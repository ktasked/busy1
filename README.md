# Utility Monitoring Platform - Comprehensive SaaS Architecture

## Overview

This platform enables small businesses and housing management companies to monitor and optimize utility consumption (electricity, water, heat) through smart meter integration, ML-powered forecasting, anomaly detection, and automated subsidy applications.

---

## Project Structure

```
/workspace
├── database_schema.sql          # PostgreSQL schema with time-series optimization
├── backend/
│   ├── requirements.txt         # Python dependencies
│   ├── app/
│   │   ├── database.py          # Database configuration & session management
│   │   └── main.py              # FastAPI application with all endpoints
│   ├── models/
│   │   └── models.py            # SQLAlchemy ORM models
│   ├── schemas/
│   │   └── schemas.py           # Pydantic validation schemas
│   └── services/
│       └── services.py          # Business logic services
├── ml_models/
│   ├── forecasting.py           # Prophet-based consumption forecasting
│   ├── anomaly_detection.py     # Statistical & XGBoost anomaly detection
│   └── subsidy_automation.py    # Automated subsidy report generation
└── frontend/
    ├── package.json             # React dependencies
    └── src/components/
        └── UtilityDashboard.jsx # React dashboard component
```

---

## Database Schema Highlights

### Core Tables

1. **users** - Platform users (business owners, property managers)
2. **properties** - Business premises, apartment buildings
3. **meters** - Smart meters with unique IDs and location data
4. **utility_types** - Electricity, water, heat, gas configurations
5. **meter_readings** - Time-series consumption data (optimized with indexes)
6. **hourly/daily/monthly_summaries** - Aggregated data for fast reporting
7. **anomalies** - Detected anomalies with severity levels
8. **subsidy_reports** - Automated subsidy application tracking

### Key Features

- UUID primary keys for distributed system compatibility
- Composite unique constraints to prevent duplicate readings
- Partial indexes for efficient anomaly queries
- Foreign key cascades for data integrity
- Timezone-aware timestamps for global deployment

---

## Backend API Endpoints

### Meter Readings
- `POST /api/v1/readings/upload` - Batch upload from smart meter gateways
- `GET /api/v1/readings/{meter_id}` - Retrieve historical readings

### Aggregation (Background Tasks)
- `POST /api/v1/aggregation/hourly` - Trigger hourly summarization
- `POST /api/v1/aggregation/daily` - Trigger daily summarization

### Dashboard
- `GET /api/v1/dashboard/property/{property_id}` - Property summary
- `GET /api/v1/dashboard/savings/{property_id}` - Cost savings analysis
- `GET /api/v1/dashboard/anomalies` - Active anomalies list

### ML Features
- `GET /api/v1/forecast/{meter_id}` - 30-day consumption forecast (Prophet)
- `POST /api/v1/anomalies/detect` - Run anomaly detection (statistical/XGBoost)

### Subsidy Automation
- `POST /api/v1/subsidy/generate-report` - Generate and send subsidy report

---

## Machine Learning Components

### 1. Consumption Forecasting (Prophet)

**File:** `ml_models/forecasting.py`

**Features:**
- Fetches 1 year of historical daily data
- Handles seasonality (yearly, weekly, daily)
- Provides 95% confidence intervals
- Calculates model accuracy (MAPE)

**Usage:**
```python
from ml_models.forecasting import generate_forecast

forecast = generate_forecast(db, meter_id, days=30)
# Returns: predicted values, confidence intervals, total consumption
```

### 2. Anomaly Detection

**File:** `ml_models/anomaly_detection.py`

**Statistical Methods:**
- **Z-Score:** Flags points >3 standard deviations from mean
- **IQR Method:** Robust outlier detection using interquartile range
- **Moving Average:** Detects deviations from rolling averages

**ML Method (XGBoost):**
- Feature engineering: time features, lag features, rolling statistics
- Trained on labeled data (or pseudo-labels from statistical methods)
- Handles imbalanced data with scale_pos_weight

**Ensemble Approach:**
- Combines multiple methods
- Flags as anomaly if detected by ≥2 methods
- Classifies severity: low, medium, high, critical

### 3. Subsidy Application Automation

**File:** `ml_models/subsidy_automation.py`

**Trigger Conditions:**
- Severity level: high or critical
- Deviation percentage > 100%
- Continuous high consumption over weekend/holiday
- Unresolved anomaly with no prior report

**Report Contents:**
- Property and meter information
- Anomaly details with expected vs actual values
- 30-day historical consumption data
- Estimated excess cost and carbon footprint
- Formal subsidy request section

**Output Formats:** JSON or XML
**Delivery:** Email or API endpoint to utility provider

---

## Frontend Dashboard

**File:** `frontend/src/components/UtilityDashboard.jsx`

### Components

1. **Summary Cards**
   - Total consumption today
   - Total cost today
   - Cost savings vs baseline (with percentage)
   - Active anomalies count

2. **Real-time Chart**
   - Line chart comparing actual vs predicted consumption
   - Configurable time range (24h, 7d, 30d)
   - Utility type selector (electricity, water, heat)

3. **Anomalies List**
   - Color-coded severity indicators
   - Deviation percentage and values
   - Actions: Mark Resolved, Generate Subsidy Report

4. **Forecast Chart**
   - 30-day area chart with confidence bands
   - Model accuracy display
   - Total predicted consumption

### Technologies
- React 18 with hooks
- Recharts for data visualization
- Tailwind CSS for styling
- Lucide React for icons

---

## Deployment Instructions

### Backend Setup

```bash
cd /workspace/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://user:password@localhost:5432/utility_monitoring"
export UTILITY_PROVIDER_ENDPOINT_NYC="subsidy@nyc-utility.gov"

# Initialize database
psql -U postgres -f ../database_schema.sql

# Run the application
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend Setup

```bash
cd /workspace/frontend

# Install dependencies
npm install

# Set environment variable
echo "REACT_APP_API_URL=http://localhost:8000/api/v1" > .env

# Start development server
npm start
```

### Production Considerations

1. **Database:** Use managed PostgreSQL (AWS RDS, Google Cloud SQL)
2. **Task Queue:** Configure Celery with Redis for background aggregation
3. **Caching:** Add Redis for frequently accessed summaries
4. **Monitoring:** Implement Prometheus + Grafana for metrics
5. **Security:** Add JWT authentication, rate limiting, CORS configuration
6. **Scaling:** Deploy behind load balancer with horizontal pod autoscaling

---

## Algorithm Details

### Background Aggregation Task

Runs daily to aggregate raw readings:

```python
def run_daily_aggregation_task(db):
    # 1. Aggregate raw readings into daily summaries
    AggregationService.aggregate_daily(db)
    
    # 2. Run anomaly detection on aggregated data
    detect_anomalies_statistical(db)
    
    # 3. Check for subsidy-qualifying anomalies
    check_and_trigger_subsidy_reports(db)
```

### Subsidy Automation Algorithm

```
FOR each unresolved anomaly:
    IF severity IN ['high', 'critical'] 
       AND deviation_percentage > 100
       AND subsidy_report_sent == False:
       
        1. Fetch complete anomaly details
        2. Fetch 30-day historical consumption
        3. Generate JSON/XML report with:
           - Property/meter information
           - Anomaly analysis
           - Excess cost calculation
           - Historical data
        4. Send to utility provider endpoint
        5. Update anomaly and subsidy_report tables
        6. Log success/failure
```

---

## API Request Examples

### Upload Meter Readings

```bash
curl -X POST http://localhost:8000/api/v1/readings/upload \
  -H "Content-Type: application/json" \
  -d '{
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
  }'
```

### Get Forecast

```bash
curl http://localhost:8000/api/v1/forecast/550e8400-e29b-41d4-a716-446655440000?days=30
```

### Generate Subsidy Report

```bash
curl -X POST http://localhost:8000/api/v1/subsidy/generate-report \
  -H "Content-Type: application/json" \
  -d '{
    "anomaly_id": "anomaly-uuid-here",
    "recipient_endpoint": "subsidy@utility-provider.com",
    "report_format": "JSON",
    "include_historical_data": true,
    "days_of_history": 30
  }'
```

---

## License

MIT License

## Support

For questions or issues, contact: support@utility-monitoring.example.com
