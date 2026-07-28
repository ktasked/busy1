"""
FastAPI application for the Utility Monitoring Platform.
Main entry point with API endpoints.
"""
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
from uuid import UUID

from app.database import get_db, init_db
from schemas.schemas import (
    MeterReadingBatch, MeterReadingCreate, UploadResponse,
    MeterReadingResponse, AnomalyResponse, ForecastResponse,
    DashboardSummary, PropertySummary, SubsidyReportRequest,
    SubsidyReportResponse
)
from services.services import ReadingService, AggregationService, DashboardService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title="Utility Monitoring Platform API",
    description="API for monitoring and optimizing utility consumption (electricity, water, heat)",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logger.info("Starting up Utility Monitoring Platform...")
    init_db()
    logger.info("Database initialized successfully")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down Utility Monitoring Platform...")


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


# ============================================================================
# METER READINGS ENDPOINTS
# ============================================================================

@app.post("/api/v1/readings/upload", response_model=UploadResponse)
async def upload_meter_readings(
    batch: MeterReadingBatch,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Upload meter readings from smart meter gateways.
    
    Accepts JSON data containing one or more meter readings.
    Validates incoming data, parses it, and saves to the MeterReadings table.
    
    Request body example:
    {
        "readings": [
            {
                "meter_id": "550e8400-e29b-41d4-a716-446655440000",
                "reading_timestamp": "2024-01-15T10:30:00Z",
                "consumption_value": 125.5,
                "unit_of_measurement": "kWh",
                "reading_type": "automatic",
                "temperature_ambient": 22.5
            }
        ]
    }
    """
    messages = []
    readings_processed = 0
    readings_failed = 0
    errors = []
    
    for reading_data in batch.readings:
        try:
            # Validate the reading
            is_valid, validation_msg = ReadingService.validate_reading(
                db, 
                reading_data.meter_id,
                reading_data.model_dump()
            )
            
            if not is_valid:
                readings_failed += 1
                errors.append({
                    "meter_id": str(reading_data.meter_id),
                    "timestamp": str(reading_data.reading_timestamp),
                    "error": validation_msg
                })
                logger.warning(f"Validation failed for meter {reading_data.meter_id}: {validation_msg}")
                continue
            
            # Save the reading
            reading = ReadingService.save_reading(
                db,
                reading_data.meter_id,
                reading_data.model_dump()
            )
            
            readings_processed += 1
            messages.append(f"Reading saved for meter {reading_data.meter_id}")
            
            # Check for anomalies (simple threshold check)
            if reading_data.consumption_value > 1000:  # Example threshold
                messages.append(f"High consumption detected for meter {reading_data.meter_id}")
                
        except Exception as e:
            readings_failed += 1
            errors.append({
                "meter_id": str(reading_data.meter_id),
                "timestamp": str(reading_data.reading_timestamp),
                "error": str(e)
            })
            logger.error(f"Error processing reading for meter {reading_data.meter_id}: {str(e)}")
    
    # Commit all successful readings
    db.commit()
    
    success = readings_processed > 0 and readings_failed == 0
    
    return UploadResponse(
        success=success,
        messages=messages,
        readings_processed=readings_processed,
        readings_failed=readings_failed,
        errors=errors if errors else None
    )


@app.get("/api/v1/readings/{meter_id}", response_model=List[MeterReadingResponse])
async def get_meter_readings(
    meter_id: UUID,
    start_date: datetime = None,
    end_date: datetime = None,
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    """Get meter readings for a specific meter within a date range."""
    from models.models import MeterReading
    
    query = db.query(MeterReading).filter(MeterReading.meter_id == meter_id)
    
    if start_date:
        query = query.filter(MeterReading.reading_timestamp >= start_date)
    if end_date:
        query = query.filter(MeterReading.reading_timestamp <= end_date)
    
    readings = query.order_by(MeterReading.reading_timestamp.desc()).limit(limit).all()
    
    return readings


# ============================================================================
# AGGREGATION ENDPOINTS
# ============================================================================

@app.post("/api/v1/aggregation/hourly")
async def trigger_hourly_aggregation(
    meter_id: UUID = None,
    db: Session = Depends(get_db)
):
    """Trigger hourly aggregation manually or for a specific meter."""
    count = AggregationService.aggregate_hourly(db, meter_id)
    return {
        "status": "success",
        "summaries_created": count,
        "aggregation_type": "hourly"
    }


@app.post("/api/v1/aggregation/daily")
async def trigger_daily_aggregation(
    meter_id: UUID = None,
    db: Session = Depends(get_db)
):
    """Trigger daily aggregation manually or for a specific meter."""
    count = AggregationService.aggregate_daily(db, meter_id)
    return {
        "status": "success",
        "summaries_created": count,
        "aggregation_type": "daily"
    }


# ============================================================================
# DASHBOARD ENDPOINTS
# ============================================================================

@app.get("/api/v1/dashboard/property/{property_id}", response_model=PropertySummary)
async def get_property_dashboard(
    property_id: UUID,
    db: Session = Depends(get_db)
):
    """Get dashboard summary for a specific property."""
    summary = DashboardService.get_property_summary(db, property_id)
    
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property {property_id} not found"
        )
    
    return summary


@app.get("/api/v1/dashboard/savings/{property_id}")
async def get_cost_savings(
    property_id: UUID,
    baseline_days: int = 30,
    db: Session = Depends(get_db)
):
    """Get cost savings compared to baseline period."""
    savings = DashboardService.get_cost_savings(db, property_id, baseline_days)
    return {
        "property_id": str(property_id),
        "baseline_days": baseline_days,
        **savings
    }


@app.get("/api/v1/dashboard/anomalies")
async def get_active_anomalies(
    property_id: UUID = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get list of active (unresolved) anomalies."""
    from models.models import Anomaly, Meter
    
    query = db.query(Anomaly).filter(Anomaly.is_resolved == False)
    
    if property_id:
        # Get meters for this property
        meter_ids = db.query(Meter.meter_id).filter(
            Meter.property_id == property_id
        ).subquery()
        query = query.filter(Anomaly.meter_id.in_(meter_ids))
    
    anomalies = query.order_by(Anomaly.detection_timestamp.desc()).limit(limit).all()
    
    return [
        {
            "anomaly_id": str(a.anomaly_id),
            "meter_id": str(a.meter_id),
            "anomaly_type": a.anomaly_type,
            "severity_level": a.severity_level,
            "deviation_percentage": float(a.deviation_percentage) if a.deviation_percentage else None,
            "expected_value": float(a.expected_value) if a.expected_value else None,
            "actual_value": float(a.actual_value) if a.actual_value else None,
            "detection_timestamp": a.detection_timestamp.isoformat(),
            "description": a.description,
            "is_resolved": a.is_resolved
        }
        for a in anomalies
    ]


# ============================================================================
# FORECASTING ENDPOINTS
# ============================================================================

@app.get("/api/v1/forecast/{meter_id}", response_model=ForecastResponse)
async def get_consumption_forecast(
    meter_id: UUID,
    days: int = 30,
    db: Session = Depends(get_db)
):
    """
    Get consumption forecast for a meter using Prophet ML model.
    
    This endpoint triggers the forecasting script and returns predictions
    for the next N days with confidence intervals.
    """
    # Import the forecasting module
    from ml_models.forecasting import generate_forecast
    
    try:
        forecast_data = generate_forecast(db, meter_id, days)
        return forecast_data
    except Exception as e:
        logger.error(f"Forecast generation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecast generation failed: {str(e)}"
        )


# ============================================================================
# ANOMALY DETECTION ENDPOINTS
# ============================================================================

@app.post("/api/v1/anomalies/detect")
async def detect_anomalies(
    meter_id: UUID = None,
    method: str = "statistical",  # statistical or ml
    db: Session = Depends(get_db)
):
    """
    Run anomaly detection on meter readings.
    
    Methods:
    - statistical: Uses Z-score and IQR methods
    - ml: Uses XGBoost model (if trained)
    """
    from ml_models.anomaly_detection import detect_anomalies_statistical, detect_anomalies_ml
    
    try:
        if method == "ml":
            results = detect_anomalies_ml(db, meter_id)
        else:
            results = detect_anomalies_statistical(db, meter_id)
        
        return {
            "status": "success",
            "method": method,
            "anomalies_detected": len(results),
            "anomalies": results
        }
    except Exception as e:
        logger.error(f"Anomaly detection failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Anomaly detection failed: {str(e)}"
        )


# ============================================================================
# SUBSIDY REPORT ENDPOINTS
# ============================================================================

@app.post("/api/v1/subsidy/generate-report", response_model=SubsidyReportResponse)
async def generate_subsidy_report(
    request: SubsidyReportRequest,
    db: Session = Depends(get_db)
):
    """
    Generate and send a subsidy report for an anomaly.
    
    Creates a structured report (JSON/XML) with relevant data and sends
    it to the utility provider's endpoint.
    """
    from ml_models.subsidy_automation import generate_and_send_subsidy_report
    
    try:
        report = generate_and_send_subsidy_report(
            db,
            request.anomaly_id,
            request.recipient_endpoint,
            request.report_format,
            request.include_historical_data,
            request.days_of_history
        )
        
        return SubsidyReportResponse(
            report_id=report['report_id'],
            status=report['status'],
            sent_at=report.get('sent_at'),
            recipient_endpoint=report['recipient_endpoint'],
            report_format=report['report_format']
        )
    except Exception as e:
        logger.error(f"Subsidy report generation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Subsidy report generation failed: {str(e)}"
        )


# ============================================================================
# BACKGROUND TASKS
# ============================================================================

@app.on_event("startup")
async def start_background_tasks():
    """Start background aggregation tasks."""
    # Note: In production, use Celery, Redis Queue, or similar
    # This is a simplified example
    pass


def run_hourly_aggregation_task(db: Session):
    """Background task to run hourly aggregation."""
    logger.info("Running scheduled hourly aggregation...")
    AggregationService.aggregate_hourly(db)
    logger.info("Hourly aggregation completed")


def run_daily_aggregation_task(db: Session):
    """Background task to run daily aggregation."""
    logger.info("Running scheduled daily aggregation...")
    AggregationService.aggregate_daily(db)
    
    # Also run anomaly detection after daily aggregation
    from ml_models.anomaly_detection import detect_anomalies_statistical
    detect_anomalies_statistical(db)
    
    logger.info("Daily aggregation and anomaly detection completed")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
