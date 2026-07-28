"""
SQLAlchemy ORM models for the Utility Monitoring Platform.
"""
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, Numeric, 
    Text, ForeignKey, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database import Base


class User(Base):
    """User model for platform users (business owners, property managers)."""
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    company_name = Column(String(200))
    role = Column(String(50), default='user')
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    # Relationships
    properties = relationship("Property", back_populates="user", cascade="all, delete-orphan")


class Property(Base):
    """Property model for business premises, apartment buildings, etc."""
    __tablename__ = "properties"

    property_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    property_name = Column(String(200), nullable=False)
    property_type = Column(String(50))
    address_line1 = Column(String(255), nullable=False)
    address_line2 = Column(String(255))
    city = Column(String(100), nullable=False)
    state_province = Column(String(100))
    postal_code = Column(String(20))
    country = Column(String(100), default='USA')
    total_area_sqft = Column(Numeric(12, 2))
    year_built = Column(Integer)
    number_of_units = Column(Integer)
    timezone = Column(String(50), default='UTC')
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="properties")
    meters = relationship("Meter", back_populates="property", cascade="all, delete-orphan")


class UtilityType(Base):
    """Utility types: electricity, water, heat, gas."""
    __tablename__ = "utility_types"

    utility_type_id = Column(Integer, primary_key=True, autoincrement=True)
    utility_name = Column(String(50), unique=True, nullable=False)
    unit_of_measurement = Column(String(20), nullable=False)
    cost_per_unit = Column(Numeric(10, 6), default=0.00)
    carbon_factor = Column(Numeric(10, 6), default=0.00)
    is_active = Column(Boolean, default=True)

    # Relationships
    meters = relationship("Meter", back_populates="utility_type")


class Meter(Base):
    """Smart meters with unique IDs."""
    __tablename__ = "meters"

    meter_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.property_id", ondelete="CASCADE"), nullable=False)
    utility_type_id = Column(Integer, ForeignKey("utility_types.utility_type_id"), nullable=False)
    meter_serial_number = Column(String(100), unique=True, nullable=False, index=True)
    meter_name = Column(String(100))
    installation_date = Column(Date)
    last_maintenance_date = Column(Date)
    meter_type = Column(String(50), default='smart')
    communication_protocol = Column(String(50))
    gateway_id = Column(String(100))
    latitude = Column(Numeric(10, 8))
    longitude = Column(Numeric(11, 8))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    property = relationship("Property", back_populates="meters")
    utility_type = relationship("UtilityType", back_populates="meters")
    readings = relationship("MeterReading", back_populates="meter", cascade="all, delete-orphan")
    anomalies = relationship("Anomaly", back_populates="meter", cascade="all, delete-orphan")


class MeterReading(Base):
    """Time-series consumption data from meters."""
    __tablename__ = "meter_readings"

    reading_id = Column(Integer, primary_key=True, autoincrement=True)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False)
    reading_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    consumption_value = Column(Numeric(15, 6), nullable=False)
    unit_of_measurement = Column(String(20), nullable=False)
    reading_type = Column(String(20), default='automatic')
    quality_flag = Column(String(50), index=True)
    temperature_ambient = Column(Numeric(5, 2))
    humidity_percent = Column(Numeric(5, 2))
    voltage_level = Column(Numeric(8, 2))
    flow_rate = Column(Numeric(10, 4))
    created_at = Column(DateTime(timezone=True), default=func.now())

    __table_args__ = (
        UniqueConstraint('meter_id', 'reading_timestamp', name='uq_meter_timestamp'),
    )

    # Relationships
    meter = relationship("Meter", back_populates="readings")


class HourlySummary(Base):
    """Hourly aggregated consumption data."""
    __tablename__ = "hourly_summaries"

    summary_id = Column(Integer, primary_key=True, autoincrement=True)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False)
    hour_start = Column(DateTime(timezone=True), nullable=False)
    total_consumption = Column(Numeric(15, 6), nullable=False)
    avg_consumption = Column(Numeric(15, 6))
    min_consumption = Column(Numeric(15, 6))
    max_consumption = Column(Numeric(15, 6))
    reading_count = Column(Integer, nullable=False)
    estimated_cost = Column(Numeric(12, 2))
    created_at = Column(DateTime(timezone=True), default=func.now())

    __table_args__ = (
        UniqueConstraint('meter_id', 'hour_start', name='uq_meter_hour'),
    )


class DailySummary(Base):
    """Daily aggregated consumption data."""
    __tablename__ = "daily_summaries"

    summary_id = Column(Integer, primary_key=True, autoincrement=True)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False)
    summary_date = Column(Date, nullable=False)
    total_consumption = Column(Numeric(15, 6), nullable=False)
    avg_consumption = Column(Numeric(15, 6))
    min_consumption = Column(Numeric(15, 6))
    max_consumption = Column(Numeric(15, 6))
    peak_hour = Column(Integer)
    reading_count = Column(Integer, nullable=False)
    estimated_cost = Column(Numeric(12, 2))
    carbon_footprint = Column(Numeric(12, 4))
    created_at = Column(DateTime(timezone=True), default=func.now())

    __table_args__ = (
        UniqueConstraint('meter_id', 'summary_date', name='uq_meter_date'),
    )


class MonthlySummary(Base):
    """Monthly aggregated consumption data."""
    __tablename__ = "monthly_summaries"

    summary_id = Column(Integer, primary_key=True, autoincrement=True)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False)
    summary_month = Column(Date, nullable=False)
    total_consumption = Column(Numeric(15, 6), nullable=False)
    avg_daily_consumption = Column(Numeric(15, 6))
    min_daily_consumption = Column(Numeric(15, 6))
    max_daily_consumption = Column(Numeric(15, 6))
    peak_day = Column(Integer)
    reading_count = Column(Integer, nullable=False)
    estimated_cost = Column(Numeric(12, 2))
    carbon_footprint = Column(Numeric(12, 4))
    comparison_previous_month = Column(Numeric(8, 2))
    created_at = Column(DateTime(timezone=True), default=func.now())

    __table_args__ = (
        UniqueConstraint('meter_id', 'summary_month', name='uq_meter_month'),
    )


class Anomaly(Base):
    """Detected anomalies in consumption patterns."""
    __tablename__ = "anomalies"

    anomaly_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False)
    detection_timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    anomaly_type = Column(String(50), nullable=False)
    severity_level = Column(String(20), default='medium')
    deviation_percentage = Column(Numeric(8, 2))
    expected_value = Column(Numeric(15, 6))
    actual_value = Column(Numeric(15, 6))
    description = Column(Text)
    is_resolved = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime(timezone=True))
    resolution_notes = Column(Text)
    subsidy_report_sent = Column(Boolean, default=False)
    subsidy_report_id = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    meter = relationship("Meter", back_populates="anomalies")
    subsidy_reports = relationship("SubsidyReport", back_populates="anomaly")


class SubsidyReport(Base):
    """Automated subsidy application reports."""
    __tablename__ = "subsidy_reports"

    report_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    anomaly_id = Column(UUID(as_uuid=True), ForeignKey("anomalies.anomaly_id"))
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.property_id"), nullable=False)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id"), nullable=False)
    report_format = Column(String(20), default='JSON')
    report_data = Column(JSONB, nullable=False)
    recipient_endpoint = Column(String(255), nullable=False)
    sent_at = Column(DateTime(timezone=True))
    status = Column(String(50), default='pending')
    response_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=func.now())

    # Relationships
    anomaly = relationship("Anomaly", back_populates="subsidy_reports")
