"""
Pydantic Schemas for API Request/Response Validation
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID
from decimal import Decimal


# Meter Reading Schemas
class MeterReadingBase(BaseModel):
    meter_id: UUID
    timestamp: datetime
    value: float
    unit: str
    is_manual_entry: bool = False
    quality_flag: str = "valid"
    metadata: Optional[Dict[str, Any]] = None


class MeterReadingCreate(MeterReadingBase):
    pass


class MeterReadingResponse(MeterReadingBase):
    reading_id: int
    is_anomaly_detected: bool
    anomaly_score: Optional[float]
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class BatchReadingsUpload(BaseModel):
    readings: List[MeterReadingCreate]


# Forecast Schemas
class ForecastRequest(BaseModel):
    meter_id: UUID
    days_ahead: int = 30


class ForecastDataPoint(BaseModel):
    ds: datetime
    yhat: float
    yhat_lower: float
    yhat_upper: float


class ForecastResponse(BaseModel):
    meter_id: UUID
    forecast_period_days: int
    generated_at: datetime
    forecast: List[ForecastDataPoint]
    model_info: Dict[str, Any]


# Anomaly Detection Schemas
class AnomalyDetectionRequest(BaseModel):
    meter_id: Optional[UUID] = None
    property_id: Optional[UUID] = None
    method: str = "ensemble"  # zscore, iqr, moving_average, ensemble, xgboost
    time_range_hours: int = 24


class AnomalyDataPoint(BaseModel):
    timestamp: datetime
    value: float
    expected_value: Optional[float]
    deviation_percentage: float
    anomaly_score: float


class AnomalyResponse(BaseModel):
    anomaly_id: UUID
    meter_id: UUID
    detected_at: datetime
    anomaly_type: str
    severity: str
    deviation_percentage: float
    expected_value: Optional[float]
    actual_value: float
    description: str
    is_resolved: bool


class AnomalyDetectionResult(BaseModel):
    total_readings_analyzed: int
    anomalies_found: int
    method_used: str
    anomalies: List[AnomalyResponse]


# Dashboard Schemas
class SummaryCard(BaseModel):
    total_consumption: float
    total_cost: float
    cost_savings: float
    savings_percentage: float
    active_anomalies: int
    total_meters: int


class DashboardResponse(BaseModel):
    property_id: UUID
    property_name: str
    summary: SummaryCard
    recent_anomalies: List[AnomalyResponse]
    consumption_chart_data: List[Dict[str, Any]]
    forecast_data: Optional[List[ForecastDataPoint]]


# Subsidy Report Schemas
class SubsidyReportRequest(BaseModel):
    anomaly_id: UUID
    report_type: str = "leak_investigation"
    utility_provider_email: str


class SubsidyReportResponse(BaseModel):
    report_id: UUID
    status: str
    submission_date: Optional[datetime]
    report_data: Dict[str, Any]


# Aggregation Schemas
class AggregationRequest(BaseModel):
    meter_id: Optional[UUID] = None
    start_date: date
    end_date: date
    aggregation_level: str = "daily"  # hourly, daily, monthly


class AggregationDataPoint(BaseModel):
    period_start: datetime
    total_consumption: float
    average_consumption: float
    min_consumption: float
    max_consumption: float
    reading_count: int
    cost: float


class AggregationResponse(BaseModel):
    meter_id: UUID
    aggregation_level: str
    data_points: List[AggregationDataPoint]
