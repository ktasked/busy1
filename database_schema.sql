-- Utility Monitoring Platform Database Schema
-- PostgreSQL compatible schema with time-series optimization

-- Enable UUID extension for unique identifiers
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table: Stores platform users (business owners, property managers)
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    company_name VARCHAR(200),
    role VARCHAR(50) DEFAULT 'user' CHECK (role IN ('admin', 'manager', 'user')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT true
);

-- Properties table: Business premises, apartment buildings, etc.
CREATE TABLE properties (
    property_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    property_name VARCHAR(200) NOT NULL,
    property_type VARCHAR(50) CHECK (property_type IN ('commercial', 'residential', 'mixed', 'industrial')),
    address_line1 VARCHAR(255) NOT NULL,
    address_line2 VARCHAR(255),
    city VARCHAR(100) NOT NULL,
    state_province VARCHAR(100),
    postal_code VARCHAR(20),
    country VARCHAR(100) DEFAULT 'USA',
    total_area_sqft DECIMAL(12, 2),
    year_built INTEGER,
    number_of_units INTEGER,
    timezone VARCHAR(50) DEFAULT 'UTC',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- UtilityTypes table: Types of utilities monitored
CREATE TABLE utility_types (
    utility_type_id SERIAL PRIMARY KEY,
    utility_name VARCHAR(50) UNIQUE NOT NULL, -- 'electricity', 'water', 'heat', 'gas'
    unit_of_measurement VARCHAR(20) NOT NULL, -- 'kWh', 'gallons', 'BTU', 'therms'
    cost_per_unit DECIMAL(10, 6) DEFAULT 0.00,
    carbon_factor DECIMAL(10, 6) DEFAULT 0.00, -- kg CO2 per unit
    is_active BOOLEAN DEFAULT true
);

-- Insert default utility types
INSERT INTO utility_types (utility_name, unit_of_measurement, cost_per_unit, carbon_factor) VALUES
('electricity', 'kWh', 0.12, 0.92),
('water', 'gallons', 0.005, 0.0),
('heat', 'BTU', 0.00003, 0.05),
('gas', 'therms', 1.20, 5.3);

-- Meters table: Smart meters with unique IDs
CREATE TABLE meters (
    meter_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id UUID NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
    utility_type_id INTEGER NOT NULL REFERENCES utility_types(utility_type_id),
    meter_serial_number VARCHAR(100) UNIQUE NOT NULL,
    meter_name VARCHAR(100),
    installation_date DATE,
    last_maintenance_date DATE,
    meter_type VARCHAR(50) DEFAULT 'smart' CHECK (meter_type IN ('smart', 'manual', 'legacy')),
    communication_protocol VARCHAR(50), -- 'MQTT', 'HTTP', 'LoRaWAN', etc.
    gateway_id VARCHAR(100),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- MeterReadings table: Time-series consumption data
CREATE TABLE meter_readings (
    reading_id BIGSERIAL PRIMARY KEY,
    meter_id UUID NOT NULL REFERENCES meters(meter_id) ON DELETE CASCADE,
    reading_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    consumption_value DECIMAL(15, 6) NOT NULL,
    unit_of_measurement VARCHAR(20) NOT NULL,
    reading_type VARCHAR(20) DEFAULT 'automatic' CHECK (reading_type IN ('automatic', 'manual', 'estimated')),
    quality_flag VARCHAR(50), -- 'normal', 'anomaly_detected', 'missing', 'interpolated'
    temperature_ambient DECIMAL(5, 2), -- Optional ambient temperature
    humidity_percent DECIMAL(5, 2), -- Optional humidity
    voltage_level DECIMAL(8, 2), -- For electricity meters
    flow_rate DECIMAL(10, 4), -- For water/gas meters
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (meter_id, reading_timestamp) -- Prevent duplicate readings
);

-- Summary tables for aggregated data (faster reporting)
CREATE TABLE hourly_summaries (
    summary_id BIGSERIAL PRIMARY KEY,
    meter_id UUID NOT NULL REFERENCES meters(meter_id) ON DELETE CASCADE,
    hour_start TIMESTAMP WITH TIME ZONE NOT NULL,
    total_consumption DECIMAL(15, 6) NOT NULL,
    avg_consumption DECIMAL(15, 6),
    min_consumption DECIMAL(15, 6),
    max_consumption DECIMAL(15, 6),
    reading_count INTEGER NOT NULL,
    estimated_cost DECIMAL(12, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (meter_id, hour_start)
);

CREATE TABLE daily_summaries (
    summary_id BIGSERIAL PRIMARY KEY,
    meter_id UUID NOT NULL REFERENCES meters(meter_id) ON DELETE CASCADE,
    summary_date DATE NOT NULL,
    total_consumption DECIMAL(15, 6) NOT NULL,
    avg_consumption DECIMAL(15, 6),
    min_consumption DECIMAL(15, 6),
    max_consumption DECIMAL(15, 6),
    peak_hour INTEGER, -- Hour with highest consumption (0-23)
    reading_count INTEGER NOT NULL,
    estimated_cost DECIMAL(12, 2),
    carbon_footprint DECIMAL(12, 4), -- kg CO2
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (meter_id, summary_date)
);

CREATE TABLE monthly_summaries (
    summary_id BIGSERIAL PRIMARY KEY,
    meter_id UUID NOT NULL REFERENCES meters(meter_id) ON DELETE CASCADE,
    summary_month DATE NOT NULL, -- First day of the month
    total_consumption DECIMAL(15, 6) NOT NULL,
    avg_daily_consumption DECIMAL(15, 6),
    min_daily_consumption DECIMAL(15, 6),
    max_daily_consumption DECIMAL(15, 6),
    peak_day INTEGER, -- Day with highest consumption (1-31)
    reading_count INTEGER NOT NULL,
    estimated_cost DECIMAL(12, 2),
    carbon_footprint DECIMAL(12, 4),
    comparison_previous_month DECIMAL(8, 2), -- Percentage change
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (meter_id, summary_month)
);

-- Anomalies table: Detected anomalies and actions taken
CREATE TABLE anomalies (
    anomaly_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meter_id UUID NOT NULL REFERENCES meters(meter_id) ON DELETE CASCADE,
    detection_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    anomaly_type VARCHAR(50) NOT NULL, -- 'spike', 'leak', 'unusual_pattern', 'continuous_high'
    severity_level VARCHAR(20) DEFAULT 'medium' CHECK (severity_level IN ('low', 'medium', 'high', 'critical')),
    deviation_percentage DECIMAL(8, 2),
    expected_value DECIMAL(15, 6),
    actual_value DECIMAL(15, 6),
    description TEXT,
    is_resolved BOOLEAN DEFAULT false,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,
    subsidy_report_sent BOOLEAN DEFAULT false,
    subsidy_report_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Subsidy reports table: Track automated subsidy applications
CREATE TABLE subsidy_reports (
    report_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    anomaly_id UUID REFERENCES anomalies(anomaly_id),
    property_id UUID NOT NULL REFERENCES properties(property_id),
    meter_id UUID NOT NULL REFERENCES meters(meter_id),
    report_format VARCHAR(20) DEFAULT 'JSON' CHECK (report_format IN ('JSON', 'XML')),
    report_data JSONB NOT NULL,
    recipient_endpoint VARCHAR(255) NOT NULL, -- Email or API endpoint
    sent_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed', 'acknowledged')),
    response_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient querying
CREATE INDEX idx_meter_readings_meter_timestamp ON meter_readings (meter_id, reading_timestamp DESC);
CREATE INDEX idx_meter_readings_timestamp ON meter_readings (reading_timestamp DESC);
CREATE INDEX idx_meter_readings_quality ON meter_readings (quality_flag) WHERE quality_flag IS NOT NULL;
CREATE INDEX idx_hourly_summaries_meter_hour ON hourly_summaries (meter_id, hour_start DESC);
CREATE INDEX idx_daily_summaries_meter_date ON daily_summaries (meter_id, summary_date DESC);
CREATE INDEX idx_monthly_summaries_meter_month ON monthly_summaries (meter_id, summary_month DESC);
CREATE INDEX idx_anomalies_meter_timestamp ON anomalies (meter_id, detection_timestamp DESC);
CREATE INDEX idx_anomalies_unresolved ON anomalies (is_resolved) WHERE is_resolved = false;
CREATE INDEX idx_properties_user ON properties (user_id);
CREATE INDEX idx_meters_property ON meters (property_id);
CREATE INDEX idx_meters_utility ON meters (utility_type_id);
CREATE INDEX idx_subsidy_reports_status ON subsidy_reports (status) WHERE status != 'sent';

-- Trigger to update updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_properties_updated_at BEFORE UPDATE ON properties FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_meters_updated_at BEFORE UPDATE ON meters FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- View for real-time dashboard data
CREATE VIEW vw_current_consumption AS
SELECT 
    m.meter_id,
    m.meter_name,
    p.property_name,
    ut.utility_name,
    mr.reading_timestamp,
    mr.consumption_value,
    mr.unit_of_measurement,
    mr.quality_flag
FROM meters m
JOIN properties p ON m.property_id = p.property_id
JOIN utility_types ut ON m.utility_type_id = ut.utility_type_id
JOIN LATERAL (
    SELECT reading_timestamp, consumption_value, unit_of_measurement, quality_flag
    FROM meter_readings mr2
    WHERE mr2.meter_id = m.meter_id
    ORDER BY reading_timestamp DESC
    LIMIT 1
) mr ON true
WHERE m.is_active = true;
