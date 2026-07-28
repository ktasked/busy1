"""
Anomaly Detection for Utility Consumption.

This module provides functions to detect anomalies in meter readings
using statistical methods (Z-score, IQR) and machine learning (XGBoost).
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np
import logging
from uuid import UUID
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.models import MeterReading, Anomaly, Meter, Property, DailySummary

logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    logger.warning("XGBoost or sklearn not available. Install with: pip install xgboost scikit-learn")


# ============================================================================
# STATISTICAL ANOMALY DETECTION
# ============================================================================

def calculate_zscore_anomalies(data: pd.Series, threshold: float = 3.0) -> pd.Series:
    """
    Detect anomalies using Z-score method.
    
    Z-score measures how many standard deviations a data point is from the mean.
    Points with |z-score| > threshold are considered anomalies.
    
    Args:
        data: Series of consumption values
        threshold: Z-score threshold (default: 3.0)
    
    Returns:
        Boolean Series indicating anomalies
    """
    mean = data.mean()
    std = data.std()
    
    if std == 0:
        return pd.Series([False] * len(data), index=data.index)
    
    z_scores = np.abs((data - mean) / std)
    return z_scores > threshold


def calculate_iqr_anomalies(data: pd.Series, multiplier: float = 1.5) -> pd.Series:
    """
    Detect anomalies using Interquartile Range (IQR) method.
    
    More robust to outliers than Z-score.
    
    Args:
        data: Series of consumption values
        multiplier: IQR multiplier (default: 1.5, use 3.0 for extreme outliers)
    
    Returns:
        Boolean Series indicating anomalies
    """
    Q1 = data.quantile(0.25)
    Q3 = data.quantile(0.75)
    IQR = Q3 - Q1
    
    lower_bound = Q1 - multiplier * IQR
    upper_bound = Q3 + multiplier * IQR
    
    return (data < lower_bound) | (data > upper_bound)


def detect_moving_average_anomalies(data: pd.Series, window: int = 7, 
                                   threshold_multiplier: float = 2.0) -> pd.Series:
    """
    Detect anomalies using rolling/moving average deviation.
    
    Compares each point to a rolling average and flags significant deviations.
    
    Args:
        data: Series of consumption values
        window: Rolling window size
        threshold_multiplier: Multiplier for rolling std deviation
    
    Returns:
        Boolean Series indicating anomalies
    """
    rolling_mean = data.rolling(window=window, min_periods=1).mean()
    rolling_std = data.rolling(window=window, min_periods=1).std()
    
    # Handle zero std
    rolling_std = rolling_std.replace(0, np.nan)
    
    deviation = np.abs(data - rolling_mean) / rolling_std
    return deviation > threshold_multiplier


def detect_continuous_high_consumption(db: Session, meter_id: UUID,
                                       threshold_hours: int = 48,
                                       percentile: float = 90) -> List[Dict[str, Any]]:
    """
    Detect continuous high consumption over a period (e.g., weekend leaks).
    
    Args:
        db: Database session
        meter_id: UUID of the meter
        threshold_hours: Minimum consecutive hours of high consumption
        percentile: Percentile threshold for "high" consumption
    
    Returns:
        List of detected continuous high consumption periods
    """
    # Get recent hourly data
    start_time = datetime.utcnow() - timedelta(hours=threshold_hours * 2)
    
    hourly_data = db.query(
        DailySummary.summary_date,
        DailySummary.total_consumption
    ).filter(
        DailySummary.meter_id == meter_id,
        DailySummary.summary_date >= start_time.date()
    ).order_by(DailySummary.summary_date).all()
    
    if not hourly_data:
        return []
    
    df = pd.DataFrame([
        {'date': row.summary_date, 'consumption': float(row.total_consumption)}
        for row in hourly_data
    ])
    
    if df.empty:
        return []
    
    # Calculate threshold
    threshold_value = df['consumption'].quantile(percentile / 100)
    
    # Find consecutive periods above threshold
    df['is_high'] = df['consumption'] > threshold_value
    df['group'] = (df['is_high'] != df['is_high'].shift()).cumsum()
    
    anomalies = []
    for group_id, group_df in df[df['is_high']].groupby('group'):
        if len(group_df) >= threshold_hours / 24:  # Convert hours to days
            anomalies.append({
                'start_date': group_df['date'].min(),
                'end_date': group_df['date'].max(),
                'duration_days': len(group_df),
                'avg_consumption': group_df['consumption'].mean(),
                'threshold': threshold_value
            })
    
    return anomalies


def detect_anomalies_statistical(db: Session, meter_id: Optional[UUID] = None,
                                days: int = 30) -> List[Dict[str, Any]]:
    """
    Main function for statistical anomaly detection.
    
    Combines multiple statistical methods for comprehensive detection.
    
    Args:
        db: Database session
        meter_id: Optional specific meter ID (None for all meters)
        days: Number of days of historical data to analyze
    
    Returns:
        List of detected anomalies with details
    """
    start_time = datetime.utcnow() - timedelta(days=days)
    
    # Build query
    query = db.query(
        MeterReading.meter_id,
        MeterReading.reading_timestamp,
        MeterReading.consumption_value
    ).filter(
        MeterReading.reading_timestamp >= start_time
    )
    
    if meter_id:
        query = query.filter(MeterReading.meter_id == meter_id)
    
    query = query.order_by(MeterReading.meter_id, MeterReading.reading_timestamp)
    
    readings = query.all()
    
    if not readings:
        logger.info("No readings found for anomaly detection")
        return []
    
    # Group by meter
    meters_data = {}
    for reading in readings:
        if reading.meter_id not in meters_data:
            meters_data[reading.meter_id] = []
        meters_data[reading.meter_id].append({
            'timestamp': reading.reading_timestamp,
            'value': float(reading.consumption_value)
        })
    
    detected_anomalies = []
    
    for mid, data in meters_data.items():
        df = pd.DataFrame(data)
        
        if len(df) < 10:
            continue
        
        # Apply multiple detection methods
        zscore_anomalies = calculate_zscore_anomalies(df['value'], threshold=3.0)
        iqr_anomalies = calculate_iqr_anomalies(df['value'], multiplier=1.5)
        ma_anomalies = detect_moving_average_anomalies(df['value'], window=7)
        
        # Combine: flag as anomaly if detected by at least 2 methods
        anomaly_mask = (
            zscore_anomalies.astype(int) + 
            iqr_anomalies.astype(int) + 
            ma_anomalies.astype(int)
        ) >= 2
        
        # Get meter info
        meter = db.query(Meter).filter(Meter.meter_id == mid).first()
        property_obj = db.query(Property).join(Meter).filter(Meter.meter_id == mid).first()
        
        for idx in df[anomaly_mask].index:
            row = df.loc[idx]
            
            # Calculate expected value (rolling mean)
            expected = df['value'].rolling(window=7, min_periods=1).mean().loc[idx]
            actual = row['value']
            deviation = ((actual - expected) / expected * 100) if expected > 0 else 0
            
            # Determine severity
            if abs(deviation) > 200:
                severity = 'critical'
            elif abs(deviation) > 100:
                severity = 'high'
            elif abs(deviation) > 50:
                severity = 'medium'
            else:
                severity = 'low'
            
            # Create anomaly record
            anomaly = Anomaly(
                meter_id=mid,
                anomaly_type='spike' if deviation > 0 else 'drop',
                severity_level=severity,
                deviation_percentage=deviation,
                expected_value=expected,
                actual_value=actual,
                description=f"Consumption {'spike' if deviation > 0 else 'drop'} detected: {deviation:.1f}% deviation from expected",
                is_resolved=False
            )
            db.add(anomaly)
            
            detected_anomalies.append({
                'anomaly_id': str(anomaly.anomaly_id),
                'meter_id': str(mid),
                'property_name': property_obj.property_name if property_obj else None,
                'anomaly_type': anomaly.anomaly_type,
                'severity_level': severity,
                'deviation_percentage': round(deviation, 2),
                'expected_value': round(expected, 4),
                'actual_value': round(actual, 4),
                'detection_timestamp': row['timestamp'].isoformat(),
                'description': anomaly.description
            })
    
    db.commit()
    logger.info(f"Detected {len(detected_anomalies)} anomalies")
    
    return detected_anomalies


# ============================================================================
# MACHINE LEARNING ANOMALY DETECTION (XGBoost)
# ============================================================================

def prepare_features_for_ml(db: Session, meter_id: UUID, 
                           days: int = 90) -> pd.DataFrame:
    """
    Prepare features for ML-based anomaly detection.
    
    Features include:
    - Time-based: hour, day of week, month, is_weekend
    - Consumption patterns: lag features, rolling statistics
    - Environmental: temperature (if available)
    
    Args:
        db: Database session
        meter_id: UUID of the meter
        days: Days of historical data
    
    Returns:
        DataFrame with features
    """
    start_time = datetime.utcnow() - timedelta(days=days)
    
    readings = db.query(
        MeterReading.reading_timestamp,
        MeterReading.consumption_value,
        MeterReading.temperature_ambient
    ).filter(
        MeterReading.meter_id == meter_id,
        MeterReading.reading_timestamp >= start_time
    ).order_by(MeterReading.reading_timestamp).all()
    
    if not readings:
        return pd.DataFrame()
    
    df = pd.DataFrame([
        {
            'timestamp': r.reading_timestamp,
            'consumption': float(r.consumption_value),
            'temperature': float(r.temperature_ambient) if r.temperature_ambient else None
        }
        for r in readings
    ])
    
    # Time-based features
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['month'] = df['timestamp'].dt.month
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    df['is_business_hours'] = ((df['hour'] >= 8) & (df['hour'] <= 18)).astype(int)
    
    # Lag features
    for lag in [1, 2, 3, 6, 12, 24]:
        df[f'lag_{lag}h'] = df['consumption'].shift(lag)
    
    # Rolling statistics
    for window in [6, 12, 24]:
        df[f'rolling_mean_{window}h'] = df['consumption'].rolling(window=window).mean()
        df[f'rolling_std_{window}h'] = df['consumption'].rolling(window=window).std()
    
    # Deviation from rolling mean
    df['deviation_from_mean'] = df['consumption'] - df['rolling_mean_24h']
    df['deviation_percentage'] = df['deviation_from_mean'] / df['rolling_mean_24h'] * 100
    
    # Drop rows with NaN from lag/rolling features
    df = df.dropna()
    
    return df


def train_xgboost_anomaly_detector(df: pd.DataFrame, 
                                   contamination: float = 0.05) -> Tuple[xgb.XGBClassifier, StandardScaler]:
    """
    Train an XGBoost model for anomaly detection.
    
    This requires labeled data (normal vs anomalous). In practice, you would:
    1. Use historical data with known anomalies
    2. Generate synthetic anomalies for training
    3. Use unsupervised approaches first, then refine with labels
    
    Args:
        df: Feature DataFrame
        contamination: Expected proportion of anomalies
    
    Returns:
        Trained model and scaler
    """
    if not XGBOOST_AVAILABLE:
        raise ImportError("XGBoost not available")
    
    # Define feature columns (exclude timestamp and target)
    feature_cols = [col for col in df.columns 
                   if col not in ['timestamp', 'consumption', 'is_anomaly']]
    
    X = df[feature_cols].values
    y = df.get('is_anomaly', pd.Series([0] * len(df))).values  # Default to no labels
    
    # If no labels, use statistical methods to generate pseudo-labels
    if y.sum() == 0:
        zscore_anomalies = calculate_zscore_anomalies(pd.Series(df['consumption']))
        y = zscore_anomalies.astype(int).values
    
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if y.sum() > 0 else None
    )
    
    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Calculate scale_pos_weight for imbalanced data
    neg_count = (y_train == 0).sum()
    pos_count = (y_train == 1).sum()
    scale_pos_weight = neg_count / pos_count if pos_count > 0 else 1
    
    # Train XGBoost
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        eval_metric='logloss'
    )
    
    model.fit(X_train_scaled, y_train)
    
    # Evaluate
    train_score = model.score(X_train_scaled, y_train)
    test_score = model.score(X_test_scaled, y_test)
    
    logger.info(f"XGBoost model trained - Train accuracy: {train_score:.4f}, Test accuracy: {test_score:.4f}")
    
    return model, scaler


def detect_anomalies_ml(db: Session, meter_id: Optional[UUID] = None,
                       use_pretrained: bool = True) -> List[Dict[str, Any]]:
    """
    Detect anomalies using ML model (XGBoost).
    
    Args:
        db: Database session
        meter_id: Optional specific meter ID
        use_pretrained: Whether to use a pretrained model
    
    Returns:
        List of detected anomalies
    """
    if not XGBOOST_AVAILABLE:
        logger.warning("XGBoost not available, falling back to statistical methods")
        return detect_anomalies_statistical(db, meter_id)
    
    # For now, fall back to statistical methods
    # In production, you would load a pretrained model and use it for prediction
    logger.info("ML anomaly detection called - using statistical fallback")
    return detect_anomalies_statistical(db, meter_id)


def save_model(model: xgb.XGBClassifier, scaler: StandardScaler, 
              filepath: str = "models/xgboost_anomaly_detector.json"):
    """Save trained model and scaler."""
    import json
    from sklearn.externals import joblib
    
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    model.save_model(filepath.replace('.json', '.model'))
    joblib.dump(scaler, filepath.replace('.json', '.scaler.pkl'))
    logger.info(f"Model saved to {filepath}")


def load_model(filepath: str = "models/xgboost_anomaly_detector.model") -> xgb.XGBClassifier:
    """Load pretrained model."""
    if not XGBOOST_AVAILABLE:
        return None
    
    model = xgb.XGBClassifier()
    model.load_model(filepath)
    return model


if __name__ == "__main__":
    print("Anomaly detection module loaded successfully")
    print(f"XGBoost available: {XGBOOST_AVAILABLE}")
