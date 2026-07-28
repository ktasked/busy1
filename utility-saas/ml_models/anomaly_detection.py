"""
Anomaly Detection for Utility Consumption

This module provides multiple methods for detecting anomalies in utility
consumption patterns:
1. Statistical methods (Z-score, IQR)
2. Moving average deviation
3. Ensemble approach combining multiple methods
4. XGBoost-based ML detection (for labeled data)
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import logging
import math

logger = logging.getLogger(__name__)


def detect_anomalies(
    db: Session,
    meter_id: Optional[str] = None,
    property_id: Optional[str] = None,
    method: str = "ensemble",
    time_range_hours: int = 24
) -> Dict[str, Any]:
    """
    Detect anomalies using specified method.
    
    Args:
        db: Database session
        meter_id: Specific meter to analyze (optional)
        property_id: Analyze all meters in property (optional)
        method: Detection method (zscore, iqr, moving_average, ensemble, xgboost)
        time_range_hours: Hours of historical data to analyze
    
    Returns:
        Dictionary with detected anomalies and statistics
    """
    # Import models
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from models.models import MeterReading, Meter, Anomaly
    
    # Get meter IDs to analyze
    meter_ids = []
    if meter_id:
        meter_ids = [meter_id]
    elif property_id:
        meters = db.query(Meter).filter(Meter.property_id == property_id).all()
        meter_ids = [str(m.meter_id) for m in meters]
    else:
        raise ValueError("Either meter_id or property_id must be provided")
    
    if not meter_ids:
        return {
            "total_readings_analyzed": 0,
            "anomalies_found": 0,
            "method_used": method,
            "anomalies": []
        }
    
    # Get readings within time range
    cutoff_time = datetime.now() - timedelta(hours=time_range_hours)
    
    all_anomalies = []
    total_readings = 0
    
    for mid in meter_ids:
        readings = db.query(MeterReading).filter(
            MeterReading.meter_id == mid,
            MeterReading.timestamp >= cutoff_time
        ).order_by(MeterReading.timestamp).all()
        
        if len(readings) < 5:
            continue
        
        total_readings += len(readings)
        values = [float(r.value) for r in readings]
        timestamps = [r.timestamp for r in readings]
        
        # Apply detection method
        if method == "zscore":
            anomaly_indices = detect_zscore(values, threshold=2.5)
        elif method == "iqr":
            anomaly_indices = detect_iqr(values, multiplier=1.5)
        elif method == "moving_average":
            anomaly_indices = detect_moving_average_deviation(values, window_size=5, threshold=0.3)
        elif method == "ensemble":
            anomaly_indices = detect_ensemble(values, methods=["zscore", "iqr", "moving_average"])
        elif method == "xgboost":
            # Requires labeled training data
            anomaly_indices = detect_xgboost(values, timestamps, mid)
        else:
            raise ValueError(f"Unknown method: {method}")
        
        # Create anomaly records
        for idx in anomaly_indices:
            reading = readings[idx]
            
            # Calculate expected value (mean of non-anomalous values)
            normal_values = [v for i, v in enumerate(values) if i not in anomaly_indices]
            expected = sum(normal_values) / len(normal_values) if normal_values else 0
            
            deviation = abs(values[idx] - expected) / expected * 100 if expected > 0 else 0
            
            # Determine severity
            if deviation > 100:
                severity = "critical"
            elif deviation > 50:
                severity = "high"
            elif deviation > 30:
                severity = "medium"
            else:
                severity = "low"
            
            # Determine anomaly type
            if values[idx] > expected:
                anomaly_type = "spike"
            else:
                anomaly_type = "drop"
            
            # Check for continuous high consumption (potential leak)
            if idx > 0 and values[idx-1] > expected * 1.3:
                anomaly_type = "continuous_high"
            
            anomaly_record = {
                "anomaly_id": f"{mid}-{idx}",
                "meter_id": mid,
                "detected_at": reading.timestamp.isoformat(),
                "anomaly_type": anomaly_type,
                "severity": severity,
                "deviation_percentage": round(deviation, 2),
                "expected_value": round(expected, 2),
                "actual_value": values[idx],
                "description": f"{anomaly_type.replace('_', ' ').title()} detected: {deviation:.1f}% deviation from expected",
                "is_resolved": False
            }
            
            all_anomalies.append(anomaly_record)
            
            # Update reading flag in database
            reading.is_anomaly_detected = True
            reading.anomaly_score = deviation / 100
            db.commit()
    
    # Sort by severity
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_anomalies.sort(key=lambda x: severity_order.get(x["severity"], 4))
    
    logger.info(f"Detected {len(all_anomalies)} anomalies in {total_readings} readings using {method} method")
    
    return {
        "total_readings_analyzed": total_readings,
        "anomalies_found": len(all_anomalies),
        "method_used": method,
        "anomalies": all_anomalies
    }


def detect_zscore(values: List[float], threshold: float = 2.5) -> List[int]:
    """
    Detect anomalies using Z-score method.
    
    Z-score measures how many standard deviations a value is from the mean.
    Values with |Z| > threshold are considered anomalies.
    """
    if len(values) < 3:
        return []
    
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std_dev = math.sqrt(variance)
    
    if std_dev == 0:
        return []
    
    anomaly_indices = []
    for i, value in enumerate(values):
        z_score = abs(value - mean) / std_dev
        if z_score > threshold:
            anomaly_indices.append(i)
    
    return anomaly_indices


def detect_iqr(values: List[float], multiplier: float = 1.5) -> List[int]:
    """
    Detect anomalies using Interquartile Range (IQR) method.
    
    More robust to outliers than Z-score.
    """
    if len(values) < 4:
        return []
    
    sorted_values = sorted(values)
    n = len(sorted_values)
    
    # Calculate Q1 (25th percentile) and Q3 (75th percentile)
    q1_idx = n // 4
    q3_idx = (3 * n) // 4
    
    q1 = sorted_values[q1_idx]
    q3 = sorted_values[q3_idx]
    
    iqr = q3 - q1
    lower_bound = q1 - multiplier * iqr
    upper_bound = q3 + multiplier * iqr
    
    anomaly_indices = []
    for i, value in enumerate(values):
        if value < lower_bound or value > upper_bound:
            anomaly_indices.append(i)
    
    return anomaly_indices


def detect_moving_average_deviation(
    values: List[float], 
    window_size: int = 5, 
    threshold: float = 0.3
) -> List[int]:
    """
    Detect anomalies using moving average deviation.
    
    Compares each value to the moving average of previous values.
    Good for detecting sudden changes in consumption patterns.
    """
    if len(values) <= window_size:
        return []
    
    anomaly_indices = []
    
    for i in range(window_size, len(values)):
        # Calculate moving average of previous window_size values
        window = values[i-window_size:i]
        moving_avg = sum(window) / len(window)
        
        if moving_avg > 0:
            deviation = abs(values[i] - moving_avg) / moving_avg
            if deviation > threshold:
                anomaly_indices.append(i)
    
    return anomaly_indices


def detect_ensemble(values: List[float], methods: List[str] = None) -> List[int]:
    """
    Ensemble method combining multiple detection approaches.
    
    A value is flagged as anomalous if at least 2 methods agree.
    """
    if methods is None:
        methods = ["zscore", "iqr", "moving_average"]
    
    # Get anomaly indices from each method
    method_results = {}
    
    if "zscore" in methods:
        method_results["zscore"] = set(detect_zscore(values, threshold=2.0))
    
    if "iqr" in methods:
        method_results["iqr"] = set(detect_iqr(values, multiplier=1.5))
    
    if "moving_average" in methods:
        method_results["moving_average"] = set(detect_moving_average_deviation(values, window_size=5, threshold=0.25))
    
    # Count votes for each index
    vote_counts = {}
    for method_indices in method_results.values():
        for idx in method_indices:
            vote_counts[idx] = vote_counts.get(idx, 0) + 1
    
    # Flag as anomaly if at least 2 methods agree
    anomaly_indices = [idx for idx, count in vote_counts.items() if count >= 2]
    
    return sorted(anomaly_indices)


def detect_xgboost(
    values: List[float], 
    timestamps: List[datetime], 
    meter_id: str,
    use_pretrained: bool = True
) -> List[int]:
    """
    XGBoost-based anomaly detection for labeled data.
    
    This is an outline/placeholder for advanced ML-based detection.
    In production, you would:
    1. Train on historical labeled data (normal vs anomalous)
    2. Extract features (time of day, day of week, rolling statistics, etc.)
    3. Use trained model for prediction
    
    For now, falls back to ensemble method if no trained model available.
    """
    try:
        import xgboost as xgb
        import numpy as np
        from sklearn.preprocessing import StandardScaler
        
        # Check if we have a pretrained model
        model_path = f"/tmp/xgboost_model_{meter_id}.json"
        
        if use_pretrained:
            # In production, load actual trained model
            # model = xgb.XGBClassifier()
            # model.load_model(model_path)
            pass
        
        # Feature engineering (simplified example)
        features = []
        for i, (value, ts) in enumerate(zip(values, timestamps)):
            feature_vector = [
                value,
                ts.hour,  # Time of day
                ts.weekday(),  # Day of week
                ts.day,  # Day of month
            ]
            
            # Add rolling statistics if enough history
            if i >= 5:
                window = values[i-5:i]
                feature_vector.extend([
                    sum(window) / len(window),  # Rolling mean
                    max(window) - min(window),  # Rolling range
                ])
            else:
                feature_vector.extend([0, 0])
            
            features.append(feature_vector)
        
        # In production, scale features and predict
        # X = np.array(features)
        # X_scaled = scaler.transform(X)
        # predictions = model.predict(X_scaled)
        # anomaly_indices = [i for i, pred in enumerate(predictions) if pred == 1]
        
        # Fallback to ensemble for demonstration
        logger.warning("XGBoost model not available, using ensemble fallback")
        return detect_ensemble(values)
        
    except ImportError:
        logger.warning("XGBoost or sklearn not installed, using ensemble fallback")
        return detect_ensemble(values)


def train_xgboost_model(
    db: Session,
    meter_id: str,
    output_path: str
) -> Dict[str, Any]:
    """
    Train XGBoost model on labeled anomaly data.
    
    This function outlines the training process. In production:
    1. Collect labeled historical data
    2. Extract relevant features
    3. Split into train/test sets
    4. Train model with hyperparameter tuning
    5. Evaluate and save model
    """
    try:
        import xgboost as xgb
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report
        import numpy as np
        
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from models.models import MeterReading, Anomaly
        
        # Get historical readings with anomaly labels
        cutoff_date = datetime.now() - timedelta(days=365)
        readings = db.query(MeterReading).filter(
            MeterReading.meter_id == meter_id,
            MeterReading.timestamp >= cutoff_date
        ).order_by(MeterReading.timestamp).all()
        
        if len(readings) < 100:
            return {"error": "Insufficient training data"}
        
        # Prepare features and labels
        X = []
        y = []
        
        for i, reading in enumerate(readings):
            # Features
            features = [
                float(reading.value),
                reading.timestamp.hour,
                reading.timestamp.weekday(),
                reading.timestamp.day,
            ]
            
            # Rolling statistics
            if i >= 10:
                window = [float(readings[j].value) for j in range(i-10, i)]
                features.extend([
                    sum(window) / len(window),
                    max(window) - min(window),
                ])
            else:
                features.extend([0, 0])
            
            X.append(features)
            
            # Label (1 if anomaly, 0 otherwise)
            y.append(1 if reading.is_anomaly_detected else 0)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        # Train XGBoost
        model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            scale_pos_weight=sum(y_train) / (len(y_train) - sum(y_train))  # Handle class imbalance
        )
        
        model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = model.predict(X_test)
        report = classification_report(y_test, y_pred, output_dict=True)
        
        # Save model
        model.save_model(output_path)
        
        return {
            "status": "success",
            "model_path": output_path,
            "training_samples": len(X_train),
            "test_samples": len(X_test),
            "accuracy": report["accuracy"],
            "precision": report["weighted avg"]["precision"],
            "recall": report["weighted avg"]["recall"],
            "f1_score": report["weighted avg"]["f1-score"]
        }
        
    except ImportError as e:
        return {"error": f"Required libraries not installed: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}
