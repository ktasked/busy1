"""
Prophet-based Electricity Consumption Forecasting

This module uses Facebook's Prophet library to forecast future electricity
consumption based on historical meter readings.
"""
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging
import pandas as pd

logger = logging.getLogger(__name__)

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    logger.warning("Prophet library not installed. Install with: pip install prophet")


def generate_forecast(
    db: Session,
    meter_id: str,
    days_ahead: int = 30,
    include_seasonality: bool = True
) -> Dict[str, Any]:
    """
    Generate electricity consumption forecast using Prophet.
    
    Args:
        db: Database session
        meter_id: UUID of the meter to forecast
        days_ahead: Number of days to forecast ahead
        include_seasonality: Whether to include weekly/yearly seasonality
    
    Returns:
        Dictionary containing forecast data points with confidence intervals
    """
    if not PROPHET_AVAILABLE:
        raise ImportError("Prophet library is not available")
    
    # Import models
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from models.models import MeterReading
    
    # Query historical data (last 90 days for training)
    cutoff_date = datetime.now() - timedelta(days=90)
    
    readings = db.query(MeterReading).filter(
        MeterReading.meter_id == meter_id,
        MeterReading.timestamp >= cutoff_date,
        MeterReading.quality_flag == 'valid'
    ).order_by(MeterReading.timestamp).all()
    
    if len(readings) < 10:
        raise ValueError(f"Insufficient historical data for meter {meter_id}. Need at least 10 readings.")
    
    # Prepare data for Prophet (requires 'ds' for timestamp and 'y' for value)
    df = pd.DataFrame([
        {
            'ds': r.timestamp,
            'y': float(r.value)
        }
        for r in readings
    ])
    
    # Remove any duplicates by timestamp
    df = df.drop_duplicates(subset=['ds'], keep='last')
    
    # Initialize Prophet model
    model = Prophet(
        daily_seasonality=True,
        weekly_seasonality=include_seasonality,
        yearly_seasonality=include_seasonality,
        interval_width=0.95,  # 95% confidence interval
        uncertainty_samples=1000
    )
    
    # Fit the model
    logger.info(f"Training Prophet model on {len(df)} data points...")
    model.fit(df)
    
    # Create future dataframe for forecasting
    future = model.make_future_dataframe(periods=days_ahead, freq='D')
    
    # Make predictions
    forecast = model.predict(future)
    
    # Extract forecasted values (only future dates)
    future_forecast = forecast[forecast['ds'] > datetime.now()]
    
    # Format results
    forecast_data = []
    for _, row in future_forecast.iterrows():
        forecast_data.append({
            'ds': row['ds'].to_pydatetime() if hasattr(row['ds'], 'to_pydatetime') else row['ds'],
            'yhat': float(row['yhat']),
            'yhat_lower': float(row['yhat_lower']),
            'yhat_upper': float(row['yhat_upper'])
        })
    
    # Get model info
    model_info = {
        'model': 'prophet',
        'version': '1.1.5',
        'training_samples': len(df),
        'forecast_period_days': days_ahead,
        'features': {
            'daily_seasonality': True,
            'weekly_seasonality': include_seasonality,
            'yearly_seasonality': include_seasonality
        }
    }
    
    logger.info(f"Generated {len(forecast_data)} day forecast for meter {meter_id}")
    
    return {
        'meter_id': meter_id,
        'forecast_period_days': days_ahead,
        'generated_at': datetime.now(),
        'forecast': forecast_data,
        'model_info': model_info
    }


def get_feature_importance(db: Session, meter_id: str) -> Dict[str, Any]:
    """
    Analyze feature importance from the Prophet model.
    
    Returns information about trend, weekly, and yearly components.
    """
    if not PROPHET_AVAILABLE:
        raise ImportError("Prophet library is not available")
    
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from models.models import MeterReading
    
    # Get historical data
    cutoff_date = datetime.now() - timedelta(days=90)
    readings = db.query(MeterReading).filter(
        MeterReading.meter_id == meter_id,
        MeterReading.timestamp >= cutoff_date
    ).order_by(MeterReading.timestamp).all()
    
    if len(readings) < 10:
        raise ValueError("Insufficient data for feature analysis")
    
    df = pd.DataFrame([
        {'ds': r.timestamp, 'y': float(r.value)}
        for r in readings
    ]).drop_duplicates(subset=['ds'], keep='last')
    
    # Train model
    model = Prophet()
    model.fit(df)
    
    # Get components
    forecast = model.predict(df)
    
    # Extract component statistics
    components = ['trend', 'weekly', 'yearly']
    component_stats = {}
    
    for comp in components:
        if comp in forecast.columns:
            component_stats[comp] = {
                'mean': float(forecast[comp].mean()),
                'std': float(forecast[comp].std()),
                'min': float(forecast[comp].min()),
                'max': float(forecast[comp].max())
            }
    
    return {
        'meter_id': meter_id,
        'analysis_date': datetime.now(),
        'component_analysis': component_stats
    }


def compare_forecast_with_actual(
    db: Session,
    meter_id: str,
    forecast_horizon_days: int = 7
) -> Dict[str, Any]:
    """
    Compare previous forecast with actual values to evaluate model accuracy.
    
    Calculates MAPE (Mean Absolute Percentage Error) and other metrics.
    """
    if not PROPHET_AVAILABLE:
        raise ImportError("Prophet library is not available")
    
    import sys
    import os
    from uuid import UUID
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from models.models import MeterReading
    
    # Get actual readings for the past forecast_horizon_days
    start_date = datetime.now() - timedelta(days=forecast_horizon_days)
    actual_readings = db.query(MeterReading).filter(
        MeterReading.meter_id == meter_id,
        MeterReading.timestamp >= start_date
    ).all()
    
    if len(actual_readings) < forecast_horizon_days:
        return {
            'error': 'Insufficient actual data for comparison',
            'actual_readings_count': len(actual_readings)
        }
    
    # Aggregate actual readings by day
    actual_daily = {}
    for reading in actual_readings:
        date_key = reading.timestamp.date()
        if date_key not in actual_daily:
            actual_daily[date_key] = []
        actual_daily[date_key].append(float(reading.value))
    
    actual_values = {
        date: sum(values) / len(values)  # Average for the day
        for date, values in actual_daily.items()
    }
    
    # Generate forecast that would have been made forecast_horizon_days ago
    # (simplified - in production you'd use a proper backtesting approach)
    cutoff_date = start_date - timedelta(days=90)
    training_readings = db.query(MeterReading).filter(
        MeterReading.meter_id == meter_id,
        MeterReading.timestamp >= cutoff_date,
        MeterReading.timestamp < start_date
    ).all()
    
    if len(training_readings) < 10:
        return {'error': 'Insufficient training data'}
    
    train_df = pd.DataFrame([
        {'ds': r.timestamp, 'y': float(r.value)}
        for r in training_readings
    ]).drop_duplicates(subset=['ds'], keep='last')
    
    model = Prophet()
    model.fit(train_df)
    
    # Make forecast for the comparison period
    future = model.make_future_dataframe(periods=forecast_horizon_days, freq='D')
    forecast = model.predict(future)
    
    # Get forecasted values for the comparison period
    forecast_values = {}
    for _, row in forecast.iterrows():
        if hasattr(row['ds'], 'date'):
            date_key = row['ds'].date()
        else:
            date_key = row['ds'].date()
        if date_key >= start_date.date():
            forecast_values[date_key] = row['yhat']
    
    # Calculate accuracy metrics
    errors = []
    for date_key, actual in actual_values.items():
        if date_key in forecast_values:
            predicted = forecast_values[date_key]
            if actual > 0:
                error = abs(actual - predicted) / actual * 100
                errors.append(error)
    
    mape = sum(errors) / len(errors) if errors else None
    
    return {
        'meter_id': meter_id,
        'comparison_period_days': forecast_horizon_days,
        'mape_percentage': round(mape, 2) if mape else None,
        'mean_absolute_error': round(sum(errors) / len(errors), 2) if errors else None,
        'data_points_compared': len(errors),
        'accuracy_rating': 'good' if (mape and mape < 10) else 'moderate' if (mape and mape < 20) else 'needs_improvement'
    }
