"""
SQLAlchemy ORM Models for Utility Monitoring SaaS
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Date, Numeric, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
import uuid


class User(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    company_name = Column(String(255))
    role = Column(String(50), nullable=False, default='user')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    properties = relationship("Property", back_populates="user")


class UtilityType(Base):
    __tablename__ = "utility_types"

    utility_type_id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    unit_of_measurement = Column(String(50), nullable=False)
    price_per_unit = Column(Numeric(10, 4), nullable=False, default=0.00)
    currency = Column(String(3), default='USD')

    meters = relationship("Meter", back_populates="utility_type")


class Property(Base):
    __tablename__ = "properties"

    property_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=False)
    city = Column(String(100), nullable=False)
    country = Column(String(100), nullable=False)
    postal_code = Column(String(20))
    property_type = Column(String(50), nullable=False)
    total_area = Column(Numeric(10, 2))
    number_of_units = Column(Integer)
    year_built = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="properties")
    meters = relationship("Meter", back_populates="property")


class Meter(Base):
    __tablename__ = "meters"

    meter_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.property_id", ondelete="CASCADE"), nullable=False)
    utility_type_id = Column(Integer, ForeignKey("utility_types.utility_type_id"), nullable=False)
    meter_serial_number = Column(String(100), unique=True, nullable=False)
    meter_name = Column(String(255))
    installation_date = Column(Date, nullable=False)
    last_calibration_date = Column(Date)
    next_calibration_date = Column(Date)
    is_active = Column(Boolean, default=True)
    communication_protocol = Column(String(50))
    gateway_id = Column(String(100))
    location_description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    property = relationship("Property", back_populates="meters")
    utility_type = relationship("UtilityType", back_populates="meters")
    readings = relationship("MeterReading", back_populates="meter")
    anomalies = relationship("Anomaly", back_populates="meter")


class MeterReading(Base):
    __tablename__ = "meter_readings"

    reading_id = Column(Integer, primary_key=True)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    value = Column(Numeric(15, 4), nullable=False)
    unit = Column(String(50), nullable=False)
    is_manual_entry = Column(Boolean, default=False)
    is_anomaly_detected = Column(Boolean, default=False)
    anomaly_score = Column(Numeric(5, 4))
    quality_flag = Column(String(50), default='valid')
    source = Column(String(50), default='automatic')
    metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meter = relationship("Meter", back_populates="readings")


class HourlySummary(Base):
    __tablename__ = "hourly_summaries"

    summary_id = Column(Integer, primary_key=True)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False)
    hour_start = Column(DateTime(timezone=True), nullable=False)
    total_consumption = Column(Numeric(15, 4), nullable=False)
    average_consumption = Column(Numeric(15, 4))
    min_consumption = Column(Numeric(15, 4))
    max_consumption = Column(Numeric(15, 4))
    reading_count = Column(Integer, nullable=False)
    cost = Column(Numeric(15, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('meter_id', 'hour_start'),
    )


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    summary_id = Column(Integer, primary_key=True)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    total_consumption = Column(Numeric(15, 4), nullable=False)
    average_consumption = Column(Numeric(15, 4))
    min_consumption = Column(Numeric(15, 4))
    max_consumption = Column(Numeric(15, 4))
    peak_hour = Column(Integer)
    reading_count = Column(Integer, nullable=False)
    cost = Column(Numeric(15, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('meter_id', 'date'),
    )


class MonthlySummary(Base):
    __tablename__ = "monthly_summaries"

    summary_id = Column(Integer, primary_key=True)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    total_consumption = Column(Numeric(15, 4), nullable=False)
    average_daily_consumption = Column(Numeric(15, 4))
    min_daily_consumption = Column(Numeric(15, 4))
    max_daily_consumption = Column(Numeric(15, 4))
    peak_day = Column(Integer)
    reading_count = Column(Integer, nullable=False)
    cost = Column(Numeric(15, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('meter_id', 'year', 'month'),
    )


class Anomaly(Base):
    __tablename__ = "anomalies"

    anomaly_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False)
    reading_id = Column(Integer, ForeignKey("meter_readings.reading_id", ondelete="SET NULL"))
    detected_at = Column(DateTime(timezone=True), nullable=False)
    anomaly_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    deviation_percentage = Column(Numeric(8, 2), nullable=False)
    expected_value = Column(Numeric(15, 4))
    actual_value = Column(Numeric(15, 4), nullable=False)
    description = Column(Text)
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True))
    resolution_notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meter = relationship("Meter", back_populates="anomalies")


class SubsidyReport(Base):
    __tablename__ = "subsidy_reports"

    report_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    anomaly_id = Column(UUID(as_uuid=True), ForeignKey("anomalies.anomaly_id", ondelete="SET NULL"))
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.property_id", ondelete="CASCADE"), nullable=False)
    meter_id = Column(UUID(as_uuid=True), ForeignKey("meters.meter_id", ondelete="CASCADE"), nullable=False)
    report_type = Column(String(50), nullable=False)
    status = Column(String(50), default='draft')
    submission_date = Column(DateTime(timezone=True))
    utility_provider_email = Column(String(255))
    report_data = Column(JSONB, nullable=False)
    response_data = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
