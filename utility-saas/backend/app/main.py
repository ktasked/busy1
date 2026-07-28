"""
FastAPI Main Application for Utility Monitoring SaaS
"""
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date
import logging
import sys
import os

# Configure path imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_db, init_db
from schemas.schemas import (
    MeterReadingCreate, MeterReadingResponse, BatchReadingsUpload,
    ForecastResponse, AnomalyDetectionRequest, AnomalyDetectionResult,
    DashboardResponse, SubsidyReportRequest, SubsidyReportResponse
)
from services.services import ReadingService, AggregationService, DashboardService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Utility Monitoring SaaS API",
    description="API for monitoring and optimizing utility consumption",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully")


# ============================================================================
# Meter Readings Endpoints
# ============================================================================

@app.post("/api/v1/readings/upload", response_model=List[MeterReadingResponse])
async def upload_readings(
    batch_data: BatchReadingsUpload,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Upload batch meter readings from smart meter gateways.
    
    Accepts JSON data with multiple readings, validates them,
    and saves to the MeterReadings table.
    """
    try:
        readings_data = []
        for reading in batch_data.readings:
            # Validate and prepare data
            reading_dict = {
                "meter_id": reading.meter_id,
                "timestamp": reading.timestamp,
                "value": reading.value,
                "unit": reading.unit,
                "is_manual_entry": reading.is_manual_entry,
                "quality_flag": reading.quality_flag,
                "metadata": reading.metadata,
                "source": "automatic" if not reading.is_manual_entry else "manual"
            }
            readings_data.append(reading_dict)
        
        # Batch insert readings
        saved_readings = ReadingService.batch_create_readings(db, readings_data)
        
        logger.info(f"Successfully uploaded {len(saved_readings)} readings")
        
        # Add background task for aggregation (runs after response is sent)
        if background_tasks:
            background_tasks.add_task(
                run_aggregation,
                str(saved_readings[0].meter_id) if saved_readings else None
            )
        
        return saved_readings
    
    except Exception as e:
        logger.error(f"Error uploading readings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to upload readings: {str(e)}")


@app.get("/api/v1/readings/{meter_id}", response_model=List[MeterReadingResponse])
async def get_readings(
    meter_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    """Get meter readings for a specific meter with optional time range"""
    try:
        readings = ReadingService.get_readings_by_meter(
            db=db,
            meter_id=meter_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        return readings
    except Exception as e:
        logger.error(f"Error fetching readings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch readings: {str(e)}")


# ============================================================================
# Forecasting Endpoints
# ============================================================================

@app.get("/api/v1/forecast/{meter_id}", response_model=ForecastResponse)
async def get_forecast(
    meter_id: str,
    days_ahead: int = 30,
    db: Session = Depends(get_db)
):
    """
    Generate electricity consumption forecast for a meter using Prophet ML model.
    
    Returns 30-day forecast with confidence intervals.
    """
    try:
        # Import ML model (lazy loading)
        from ml_models.forecasting import generate_forecast
        
        forecast_data = generate_forecast(
            db=db,
            meter_id=meter_id,
            days_ahead=days_ahead
        )
        
        return forecast_data
    
    except ImportError:
        logger.warning("Prophet library not available, returning mock forecast")
        # Return mock forecast if Prophet is not installed
        return create_mock_forecast(meter_id, days_ahead)
    except Exception as e:
        logger.error(f"Error generating forecast: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate forecast: {str(e)}")


# ============================================================================
# Anomaly Detection Endpoints
# ============================================================================

@app.post("/api/v1/anomalies/detect", response_model=AnomalyDetectionResult)
async def detect_anomalies(
    request: AnomalyDetectionRequest,
    db: Session = Depends(get_db)
):
    """
    Detect anomalies in consumption patterns using statistical methods or ML.
    
    Supports multiple detection methods: zscore, iqr, moving_average, ensemble, xgboost
    """
    try:
        # Import anomaly detection module
        from ml_models.anomaly_detection import detect_anomalies as run_detection
        
        result = run_detection(
            db=db,
            meter_id=request.meter_id,
            property_id=request.property_id,
            method=request.method,
            time_range_hours=request.time_range_hours
        )
        
        return result
    
    except ImportError:
        logger.warning("ML libraries not available, returning basic detection")
        # Return basic detection if ML libraries not installed
        return create_basic_anomaly_detection(db, request)
    except Exception as e:
        logger.error(f"Error detecting anomalies: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to detect anomalies: {str(e)}")


# ============================================================================
# Dashboard Endpoints
# ============================================================================

@app.get("/api/v1/dashboard/{property_id}", response_model=DashboardResponse)
async def get_dashboard(
    property_id: str,
    db: Session = Depends(get_db)
):
    """Get comprehensive dashboard data for a property"""
    try:
        dashboard_data = DashboardService.get_dashboard_data(db, property_id)
        
        # Get forecast data if available
        meters = db.query(Meter).filter(
            Meter.property_id == property_id,
            Meter.is_active == True
        ).all()
        
        forecast_data = None
        if meters:
            try:
                from ml_models.forecasting import generate_forecast
                forecast_result = generate_forecast(db, str(meters[0].meter_id), 30)
                forecast_data = forecast_result.forecast
            except:
                pass
        
        return {
            **dashboard_data,
            "consumption_chart_data": [],  # Would be populated with historical data
            "forecast_data": forecast_data
        }
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error fetching dashboard data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch dashboard data: {str(e)}")


# ============================================================================
# Subsidy Report Endpoints
# ============================================================================

@app.post("/api/v1/subsidy/generate-report", response_model=SubsidyReportResponse)
async def generate_subsidy_report(
    request: SubsidyReportRequest,
    db: Session = Depends(get_db)
):
    """
    Generate and submit subsidy report for significant anomalies.
    
    Automatically creates structured JSON/XML report and sends to utility provider.
    """
    try:
        # Import subsidy automation module
        from ml_models.subsidy_automation import generate_and_submit_report
        
        report_response = generate_and_submit_report(
            db=db,
            anomaly_id=request.anomaly_id,
            report_type=request.report_type,
            utility_provider_email=request.utility_provider_email
        )
        
        return report_response
    
    except ImportError:
        logger.warning("Subsidy automation module not available")
        raise HTTPException(status_code=503, detail="Subsidy automation service unavailable")
    except Exception as e:
        logger.error(f"Error generating subsidy report: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate subsidy report: {str(e)}")


# ============================================================================
# Aggregation Endpoints (Manual trigger for testing)
# ============================================================================

@app.post("/api/v1/aggregation/hourly")
async def trigger_hourly_aggregation(
    meter_id: Optional[str] = None,
    target_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """Manually trigger hourly aggregation (for testing/admin)"""
    try:
        AggregationService.aggregate_hourly(db, meter_id, target_date)
        return {"status": "success", "message": "Hourly aggregation completed"}
    except Exception as e:
        logger.error(f"Error in hourly aggregation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/aggregation/daily")
async def trigger_daily_aggregation(
    meter_id: Optional[str] = None,
    target_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """Manually trigger daily aggregation (for testing/admin)"""
    try:
        AggregationService.aggregate_daily(db, meter_id, target_date)
        return {"status": "success", "message": "Daily aggregation completed"}
    except Exception as e:
        logger.error(f"Error in daily aggregation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/aggregation/monthly")
async def trigger_monthly_aggregation(
    meter_id: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Manually trigger monthly aggregation (for testing/admin)"""
    try:
        AggregationService.aggregate_monthly(db, meter_id, year, month)
        return {"status": "success", "message": "Monthly aggregation completed"}
    except Exception as e:
        logger.error(f"Error in monthly aggregation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Helper Functions
# ============================================================================

def run_aggregation(meter_id: Optional[str] = None):
    """Background task to run aggregation pipelines"""
    try:
        from database import SessionLocal
        db = SessionLocal()
        
        # Run all aggregation levels
        AggregationService.aggregate_hourly(db, meter_id)
        AggregationService.aggregate_daily(db, meter_id)
        AggregationService.aggregate_monthly(db, meter_id)
        
        logger.info("Aggregation pipeline completed successfully")
    except Exception as e:
        logger.error(f"Error in background aggregation: {str(e)}")
    finally:
        db.close()


def create_mock_forecast(meter_id: str, days_ahead: int) -> ForecastResponse:
    """Create mock forecast data when Prophet is not available"""
    from datetime import timedelta
    
    forecast_points = []
    base_value = 100.0
    
    for i in range(days_ahead):
        forecast_date = datetime.now() + timedelta(days=i+1)
        forecast_points.append({
            "ds": forecast_date,
            "yhat": base_value + (i * 0.5),
            "yhat_lower": base_value + (i * 0.5) - 10,
            "yhat_upper": base_value + (i * 0.5) + 10
        })
    
    return ForecastResponse(
        meter_id=meter_id,
        forecast_period_days=days_ahead,
        generated_at=datetime.now(),
        forecast=forecast_points,
        model_info={"model": "mock", "version": "1.0"}
    )


def create_basic_anomaly_detection(db, request: AnomalyDetectionRequest) -> AnomalyDetectionResult:
    """Create basic anomaly detection when ML libraries are not available"""
    from models.models import MeterReading, Anomaly
    from uuid import uuid4
    import random
    
    # Simple threshold-based detection
    anomalies = []
    
    # Get recent readings
    query = db.query(MeterReading)
    if request.meter_id:
        query = query.filter(MeterReading.meter_id == request.meter_id)
    
    cutoff_time = datetime.now() - timedelta(hours=request.time_range_hours)
    readings = query.filter(MeterReading.timestamp >= cutoff_time).all()
    
    if readings:
        values = [float(r.value) for r in readings]
        avg_value = sum(values) / len(values)
        
        # Flag readings that deviate more than 50% from average
        for reading in readings:
            deviation = abs(float(reading.value) - avg_value) / avg_value * 100
            if deviation > 50:
                anomalies.append(AnomalyResponse(
                    anomaly_id=uuid4(),
                    meter_id=reading.meter_id,
                    detected_at=reading.timestamp,
                    anomaly_type="spike" if reading.value > avg_value else "drop",
                    severity="high" if deviation > 100 else "medium",
                    deviation_percentage=round(deviation, 2),
                    expected_value=round(avg_value, 2),
                    actual_value=float(reading.value),
                    description=f"Consumption deviation of {deviation:.1f}% from average",
                    is_resolved=False
                ))
    
    return AnomalyDetectionResult(
        total_readings_analyzed=len(readings),
        anomalies_found=len(anomalies),
        method_used="basic_threshold",
        anomalies=anomalies
    )


# Import Meter for type hints
from models.models import Meter
