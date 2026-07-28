"""
Consumption Forecasting using Facebook Prophet.

This module provides functions to forecast electricity consumption
for a given property/meter using historical data and Prophet.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
import pandas as pd
import logging
from uuid import UUID
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.models import MeterReading, Meter, UtilityType

logger = logging.getLogger(__name__)

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    logger.warning("Prophet library not available. Install with: pip install prophet")


def fetch_historical_data(db: Session, meter_id: UUID, 
                         days: int = 365) -> pd.DataFrame:
    """
    Fetch historical consumption data for a specific meter.
    
    Args:
        db: Database session
        meter_id: UUID of the meter
        days: Number of days of historical data to fetch
    
    Returns:
        DataFrame with columns 'ds' (timestamp) and 'y' (consumption value)
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Query daily aggregated data for better forecasting
    # If daily summaries exist, use them; otherwise aggregate raw readings
    from models.models import DailySummary
    
    daily_data = db.query(
        DailySummary.summary_date.label('ds'),
        DailySummary.total_consumption.label('y')
    ).filter(
        DailySummary.meter_id == meter_id,
        DailySummary.summary_date >= start_date.date()
    ).order_by(DailySummary.summary_date).all()
    
    if daily_data:
        df = pd.DataFrame([
            {'ds': row.ds, 'y': float(row.y)}
            for row in daily_data
        ])
    else:
        # Fall back to raw readings - aggregate by day
        readings = db.query(
            func.date(MeterReading.reading_timestamp).label('ds'),
            func.sum(MeterReading.consumption_value).label('y')
        ).filter(
            MeterReading.meter_id == meter_id,
            MeterReading.reading_timestamp >= start_date
        ).group_by(
            func.date(MeterReading.reading_timestamp)
        ).order_by(func.date(MeterReading.reading_timestamp)).all()
        
        df = pd.DataFrame([
            {'ds': datetime.combine(row.ds, datetime.min.time()), 'y': float(row.y)}
            for row in readings
        ])
    
    return df


def prepare_data_for_prophet(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare data in the format required by Prophet.
    
    Prophet requires:
    - 'ds': timestamp column (datetime)
    - 'y': value column (numeric)
    
    Args:
        df: Raw data DataFrame
    
    Returns:
        Prepared DataFrame ready for Prophet
    """
    if df.empty:
        return df
    
    # Ensure ds is datetime
    df['ds'] = pd.to_datetime(df['ds'])
    
    # Ensure y is numeric
    df['y'] = pd.to_numeric(df['y'], errors='coerce')
    
    # Remove rows with NaN values
    df = df.dropna(subset=['y'])
    
    # Sort by date
    df = df.sort_values('ds')
    
    return df


def train_prophet_model(df: pd.DataFrame, 
                       seasonality_mode: str = 'additive',
                       yearly_seasonality: bool = True,
                       weekly_seasonality: bool = True,
                       daily_seasonality: bool = False,
                       changepoint_prior_scale: float = 0.05) -> Optional['Prophet']:
    """
    Train a Prophet model on historical data.
    
    Args:
        df: Prepared DataFrame with 'ds' and 'y' columns
        seasonality_mode: 'additive' or 'multiplicative'
        yearly_seasonality: Enable yearly seasonality
        weekly_seasonality: Enable weekly seasonality
        daily_seasonality: Enable daily seasonality
        changepoint_prior_scale: Flexibility of trend changes
    
    Returns:
        Trained Prophet model or None if training fails
    """
    if not PROPHET_AVAILABLE:
        logger.error("Prophet library not available")
        return None
    
    if len(df) < 30:
        logger.warning(f"Insufficient data for training ({len(df)} points). Need at least 30.")
        return None
    
    try:
        model = Prophet(
            seasonality_mode=seasonality_mode,
            yearly_seasonality=yearly_seasonality,
            weekly_seasonality=weekly_seasonality,
            daily_seasonality=daily_seasonality,
            changepoint_prior_scale=changepoint_prior_scale,
            interval_width=0.95  # 95% confidence intervals
        )
        
        model.fit(df)
        logger.info("Prophet model trained successfully")
        return model
        
    except Exception as e:
        logger.error(f"Error training Prophet model: {str(e)}")
        return None


def generate_forecast(model: 'Prophet', days: int = 30) -> pd.DataFrame:
    """
    Generate forecast for the next N days.
    
    Args:
        model: Trained Prophet model
        days: Number of days to forecast
    
    Returns:
        DataFrame with forecast including confidence intervals
    """
    # Create future dataframe
    future = model.make_future_dataframe(periods=days, freq='D')
    
    # Make prediction
    forecast = model.predict(future)
    
    # Select relevant columns
    result = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']].tail(days)
    
    return result


def generate_forecast(db: Session, meter_id: UUID, 
                     days: int = 30) -> Dict[str, Any]:
    """
    Complete forecasting pipeline: fetch data, train model, generate forecast.
    
    This is the main function called by the API endpoint.
    
    Args:
        db: Database session
        meter_id: UUID of the meter to forecast
        days: Number of days to forecast
    
    Returns:
        Dictionary containing forecast data in API response format
    """
    if not PROPHET_AVAILABLE:
        raise RuntimeError("Prophet library not available. Please install it.")
    
    # Fetch historical data (1 year)
    logger.info(f"Fetching historical data for meter {meter_id}")
    df = fetch_historical_data(db, meter_id, days=365)
    
    if df.empty:
        raise ValueError(f"No historical data found for meter {meter_id}")
    
    logger.info(f"Fetched {len(df)} data points")
    
    # Prepare data
    df = prepare_data_for_prophet(df)
    
    if len(df) < 30:
        raise ValueError(f"Insufficient data for forecasting. Need at least 30 points, got {len(df)}")
    
    # Train model
    logger.info("Training Prophet model...")
    model = train_prophet_model(df)
    
    if model is None:
        raise RuntimeError("Failed to train Prophet model")
    
    # Generate forecast
    logger.info(f"Generating {days}-day forecast...")
    forecast_df = generate_forecast(model, days)
    
    # Get unit of measurement
    meter = db.query(Meter).filter(Meter.meter_id == meter_id).first()
    if not meter:
        raise ValueError(f"Meter {meter_id} not found")
    
    utility_type = db.query(UtilityType).filter(
        UtilityType.utility_type_id == meter.utility_type_id
    ).first()
    unit = utility_type.unit_of_measurement if utility_type else "units"
    
    # Calculate model accuracy (MAPE - Mean Absolute Percentage Error)
    # Use in-sample predictions for accuracy estimate
    train_pred = model.predict(df)
    mape = abs((df['y'] - train_pred['yhat']) / df['y']).mean() * 100
    
    # Format response
    data_points = []
    for _, row in forecast_df.iterrows():
        data_points.append({
            "timestamp": row['ds'].to_pydatetime(),
            "predicted_value": round(float(row['yhat']), 4),
            "lower_bound": round(float(row['yhat_lower']), 4),
            "upper_bound": round(float(row['yhat_upper']), 4)
        })
    
    total_predicted = sum(dp['predicted_value'] for dp in data_points)
    
    response = {
        "meter_id": str(meter_id),
        "forecast_start": data_points[0]['timestamp'].date(),
        "forecast_end": data_points[-1]['timestamp'].date(),
        "total_predicted_consumption": round(total_predicted, 4),
        "unit_of_measurement": unit,
        "data_points": data_points,
        "model_accuracy": round(100 - mape, 2),  # Convert MAPE to accuracy percentage
        "generated_at": datetime.utcnow()
    }
    
    logger.info(f"Forecast generated successfully for meter {meter_id}")
    return response


def compare_forecast_with_actual(db: Session, meter_id: UUID, 
                                forecast_date: date) -> Dict[str, Any]:
    """
    Compare forecasted values with actual consumption for a given date.
    
    Useful for evaluating model performance.
    
    Args:
        db: Database session
        meter_id: UUID of the meter
        forecast_date: Date to compare
    
    Returns:
        Dictionary with forecast vs actual comparison
    """
    from models.models import DailySummary
    
    # Get actual consumption
    actual = db.query(DailySummary).filter(
        DailySummary.meter_id == meter_id,
        DailySummary.summary_date == forecast_date
    ).first()
    
    if not actual:
        return {"error": f"No data found for {forecast_date}"}
    
    # In production, you would retrieve the stored forecast
    # For now, return actual value
    return {
        "meter_id": str(meter_id),
        "date": forecast_date,
        "actual_consumption": float(actual.total_consumption),
        "unit": actual.unit_of_measurement if hasattr(actual, 'unit_of_measurement') else "kWh"
    }


if __name__ == "__main__":
    # Example usage (for testing)
    print("Prophet forecasting module loaded successfully")
    print(f"Prophet available: {PROPHET_AVAILABLE}")
