"""
Pydantic schemas for request/response validation in the Utility Monitoring Platform.
"""
from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID
from enum import Enum


class ReadingType(str, Enum):
    automatic = "automatic"
    manual = "manual"
    estimated = "estimated"


class QualityFlag(str, Enum):
    normal = "normal"
    anomaly_detected = "anomaly_detected"
    missing = "missing"
    interpolated = "interpolated"


class MeterReadingCreate(BaseModel):
    """Schema for incoming meter reading data from smart meter gateways."""
    meter_id: UUID
    reading_timestamp: datetime
    consumption_value: float = Field(..., gt=0, description="Consumption value must be positive")
    unit_of_measurement: str
    reading_type: ReadingType = ReadingType.automatic
    temperature_ambient: Optional[float] = Field(None, ge=-50, le=60)
    humidity_percent: Optional[float] = Field(None, ge=0, le=100)
    voltage_level: Optional[float] = Field(None, ge=0)
    flow_rate: Optional[float] = Field(None, ge=0)

    @validator('consumption_value')
    def validate_consumption_not_negative(cls, v):
        if v < 0:
            raise ValueError('Consumption value cannot be negative')
        return v

    class Config:
        schema_extra = {
            "example": {
                "meter_id": "550e8400-e29b-41d4-a716-446655440000",
                "reading_timestamp": "2024-01-15T10:30:00Z",
                "consumption_value": 125.5,
                "unit_of_measurement": "kWh",
                "reading_type": "automatic",
                "temperature_ambient": 22.5,
                "humidity_percent": 45.0
            }
        }


class MeterReadingBatch(BaseModel):
    """Schema for batch upload of multiple meter readings."""
    readings: List[MeterReadingCreate] = Field(..., min_items=1, max_items=1000)

    class Config:
        schema_extra = {
            "example": {
                "readings": [
                    {
                        "meter_id": "550e8400-e29b-41d4-a716-446655440000",
                        "reading_timestamp": "2024-01-15T10:30:00Z",
                        "consumption_value": 125.5,
                        "unit_of_measurement": "kWh"
                    },
                    {
                        "meter_id": "550e8400-e29b-41d4-a716-446655440001",
                        "reading_timestamp": "2024-01-15T10:30:00Z",
                        "consumption_value": 85.2,
                        "unit_of_measurement": "kWh"
                    }
                ]
            }
        }


class MeterReadingResponse(BaseModel):
    """Schema for returning meter reading data."""
    reading_id: int
    meter_id: UUID
    reading_timestamp: datetime
    consumption_value: float
    unit_of_measurement: str
    reading_type: str
    quality_flag: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    """Response schema for upload endpoint."""
    success: bool
    messages: List[str]
    readings_processed: int
    readings_failed: int
    errors: Optional[List[Dict[str, Any]]] = None


class AnomalyResponse(BaseModel):
    """Schema for anomaly detection results."""
    anomaly_id: UUID
    meter_id: UUID
    anomaly_type: str
    severity_level: str
    deviation_percentage: float
    expected_value: float
    actual_value: float
    detection_timestamp: datetime
    description: str
    is_resolved: bool


class ForecastDataPoint(BaseModel):
    """Single data point in a forecast."""
    timestamp: datetime
    predicted_value: float
    lower_bound: float
    upper_bound: float


class ForecastResponse(BaseModel):
    """Response schema for consumption forecast."""
    meter_id: UUID
    forecast_start: date
    forecast_end: date
    total_predicted_consumption: float
    unit_of_measurement: str
    data_points: List[ForecastDataPoint]
    model_accuracy: Optional[float] = None
    generated_at: datetime


class DashboardSummary(BaseModel):
    """Summary data for dashboard display."""
    total_consumption: float
    total_cost: float
    cost_savings: float
    savings_percentage: float
    carbon_footprint: float
    active_anomalies: int
    last_updated: datetime


class PropertySummary(BaseModel):
    """Property summary for dashboard."""
    property_id: UUID
    property_name: str
    property_type: str
    total_meters: int
    total_consumption_today: float
    total_cost_today: float
    anomalies_count: int


class SubsidyReportRequest(BaseModel):
    """Request to generate a subsidy report."""
    anomaly_id: UUID
    recipient_endpoint: str = EmailStr
    report_format: str = "JSON"
    include_historical_data: bool = True
    days_of_history: int = 30


class SubsidyReportResponse(BaseModel):
    """Response after generating subsidy report."""
    report_id: UUID
    status: str
    sent_at: Optional[datetime]
    recipient_endpoint: str
    report_format: str
