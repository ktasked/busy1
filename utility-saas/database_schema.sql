-- Utility Monitoring SaaS Platform - Database Schema
-- PostgreSQL 14+

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    company_name VARCHAR(255),
    role VARCHAR(50) NOT NULL DEFAULT 'user', -- admin, manager, user
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Utility types reference table
CREATE TABLE utility_types (
    utility_type_id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL, -- electricity, water, heat
    unit_of_measurement VARCHAR(50) NOT NULL, -- kWh, m³, GCal
    price_per_unit DECIMAL(10, 4) NOT NULL DEFAULT 0.00,
    currency VARCHAR(3) DEFAULT 'USD'
);

-- Properties table (business premises, apartment buildings)
CREATE TABLE properties (
    property_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    address TEXT NOT NULL,
    city VARCHAR(100) NOT NULL,
    country VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20),
    property_type VARCHAR(50) NOT NULL, -- commercial, residential, mixed
    total_area DECIMAL(10, 2), -- in square meters
    number_of_units INTEGER,
    year_built INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Meters table (smart meters)
CREATE TABLE meters (
    meter_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
    utility_type_id INTEGER NOT NULL REFERENCES utility_types(utility_type_id),
    meter_serial_number VARCHAR(100) UNIQUE NOT NULL,
    meter_name VARCHAR(255),
    installation_date DATE NOT NULL,
    last_calibration_date DATE,
    next_calibration_date DATE,
    is_active BOOLEAN DEFAULT TRUE,
    communication_protocol VARCHAR(50), -- Modbus, MQTT, LoRaWAN, etc.
    gateway_id VARCHAR(100),
    location_description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Time-series Meter Readings table (raw data from smart meters)
CREATE TABLE meter_readings (
    reading_id BIGSERIAL PRIMARY KEY,
    meter_id UUID NOT NULL REFERENCES meters(meter_id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    value DECIMAL(15, 4) NOT NULL,
    unit VARCHAR(50) NOT NULL,
    is_manual_entry BOOLEAN DEFAULT FALSE,
    is_anomaly_detected BOOLEAN DEFAULT FALSE,
    anomaly_score DECIMAL(5, 4),
    quality_flag VARCHAR(50) DEFAULT 'valid', -- valid, estimated, missing, invalid
    source VARCHAR(50) DEFAULT 'automatic', -- automatic, manual, imported
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Hourly summary table for faster reporting
CREATE TABLE hourly_summaries (
    summary_id BIGSERIAL PRIMARY KEY,
    meter_id UUID NOT NULL REFERENCES meters(meter_id) ON DELETE CASCADE,
    hour_start TIMESTAMP WITH TIME ZONE NOT NULL,
    total_consumption DECIMAL(15, 4) NOT NULL,
    average_consumption DECIMAL(15, 4),
    min_consumption DECIMAL(15, 4),
    max_consumption DECIMAL(15, 4),
    reading_count INTEGER NOT NULL,
    cost DECIMAL(15, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(meter_id, hour_start)
);

-- Daily summary table
CREATE TABLE daily_summaries (
    summary_id BIGSERIAL PRIMARY KEY,
    meter_id UUID NOT NULL REFERENCES meters(meter_id) ON DELETE CASCADE,
    date DATE NOT NULL,
    total_consumption DECIMAL(15, 4) NOT NULL,
    average_consumption DECIMAL(15, 4),
    min_consumption DECIMAL(15, 4),
    max_consumption DECIMAL(15, 4),
    peak_hour INTEGER,
    reading_count INTEGER NOT NULL,
    cost DECIMAL(15, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(meter_id, date)
);

-- Monthly summary table
CREATE TABLE monthly_summaries (
    summary_id BIGSERIAL PRIMARY KEY,
    meter_id UUID NOT NULL REFERENCES meters(meter_id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    total_consumption DECIMAL(15, 4) NOT NULL,
    average_daily_consumption DECIMAL(15, 4),
    min_daily_consumption DECIMAL(15, 4),
    max_daily_consumption DECIMAL(15, 4),
    peak_day INTEGER,
    reading_count INTEGER NOT NULL,
    cost DECIMAL(15, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(meter_id, year, month)
);

-- Anomalies detection results table
CREATE TABLE anomalies (
    anomaly_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meter_id UUID NOT NULL REFERENCES meters(meter_id) ON DELETE CASCADE,
    reading_id BIGINT REFERENCES meter_readings(reading_id) ON DELETE SET NULL,
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL,
    anomaly_type VARCHAR(50) NOT NULL, -- spike, leak, drop, continuous_high
    severity VARCHAR(20) NOT NULL, -- low, medium, high, critical
    deviation_percentage DECIMAL(8, 2) NOT NULL,
    expected_value DECIMAL(15, 4),
    actual_value DECIMAL(15, 4) NOT NULL,
    description TEXT,
    is_resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Subsidy reports table
CREATE TABLE subsidy_reports (
    report_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    anomaly_id UUID REFERENCES anomalies(anomaly_id) ON DELETE SET NULL,
    property_id UUID NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
    meter_id UUID NOT NULL REFERENCES meters(meter_id) ON DELETE CASCADE,
    report_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) DEFAULT 'draft', -- draft, submitted, approved, rejected
    submission_date TIMESTAMP WITH TIME ZONE,
    utility_provider_email VARCHAR(255),
    report_data JSONB NOT NULL,
    response_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient querying
CREATE INDEX idx_meter_readings_meter_id ON meter_readings(meter_id);
CREATE INDEX idx_meter_readings_timestamp ON meter_readings(timestamp);
CREATE INDEX idx_meter_readings_meter_timestamp ON meter_readings(meter_id, timestamp DESC);
CREATE INDEX idx_meter_readings_anomaly ON meter_readings(is_anomaly_detected) WHERE is_anomaly_detected = TRUE;

CREATE INDEX idx_hourly_summaries_meter_id ON hourly_summaries(meter_id);
CREATE INDEX idx_hourly_summaries_hour ON hourly_summaries(hour_start);

CREATE INDEX idx_daily_summaries_meter_id ON daily_summaries(meter_id);
CREATE INDEX idx_daily_summaries_date ON daily_summaries(date);

CREATE INDEX idx_monthly_summaries_meter_id ON monthly_summaries(meter_id);
CREATE INDEX idx_monthly_summaries_year_month ON monthly_summaries(year, month);

CREATE INDEX idx_anomalies_meter_id ON anomalies(meter_id);
CREATE INDEX idx_anomalies_detected_at ON anomalies(detected_at DESC);
CREATE INDEX idx_anomalies_unresolved ON anomalies(is_resolved) WHERE is_resolved = FALSE;
CREATE INDEX idx_anomalies_severity ON anomalies(severity);

CREATE INDEX idx_meters_property_id ON meters(property_id);
CREATE INDEX idx_meters_utility_type ON meters(utility_type_id);
CREATE INDEX idx_meters_active ON meters(is_active) WHERE is_active = TRUE;

CREATE INDEX idx_properties_user_id ON properties(user_id);

-- Insert default utility types
INSERT INTO utility_types (name, unit_of_measurement, price_per_unit, currency) VALUES
('electricity', 'kWh', 0.12, 'USD'),
('water', 'm³', 2.50, 'USD'),
('heat', 'GCal', 45.00, 'USD')
ON CONFLICT (name) DO NOTHING;

-- View for dashboard summary
CREATE OR REPLACE VIEW dashboard_summary AS
SELECT 
    p.property_id,
    p.name as property_name,
    COUNT(DISTINCT m.meter_id) as total_meters,
    SUM(CASE WHEN a.is_resolved = FALSE THEN 1 ELSE 0 END) as active_anomalies,
    COALESCE(SUM(ds.total_consumption), 0) as total_monthly_consumption,
    COALESCE(SUM(ds.cost), 0) as total_monthly_cost
FROM properties p
LEFT JOIN meters m ON p.property_id = m.property_id AND m.is_active = TRUE
LEFT JOIN daily_summaries ds ON m.meter_id = ds.meter_id 
    AND ds.date >= date_trunc('month', CURRENT_DATE)
LEFT JOIN anomalies a ON m.meter_id = a.meter_id
GROUP BY p.property_id, p.name;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_properties_updated_at BEFORE UPDATE ON properties
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_meters_updated_at BEFORE UPDATE ON meters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_subsidy_reports_updated_at BEFORE UPDATE ON subsidy_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
