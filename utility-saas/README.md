# Utility Monitoring SaaS Platform

A comprehensive SaaS platform for small businesses and housing management companies to monitor and optimize utility consumption (electricity, water, heat).

## 📁 Project Structure

```
utility-saas/
├── database_schema.sql          # PostgreSQL database schema
├── backend/
│   ├── app/
│   │   ├── database.py          # Database configuration
│   │   └── main.py              # FastAPI application
│   ├── models/
│   │   └── models.py            # SQLAlchemy ORM models
│   ├── schemas/
│   │   └── schemas.py           # Pydantic validation schemas
│   ├── services/
│   │   └── services.py          # Business logic services
│   └── requirements.txt         # Python dependencies
├── ml_models/
│   ├── forecasting.py           # Prophet-based consumption forecasting
│   ├── anomaly_detection.py     # Statistical & ML anomaly detection
│   └── subsidy_automation.py    # Automated subsidy report generation
├── frontend/
│   ├── package.json             # React dependencies
│   └── src/components/
│       └── UtilityDashboard.jsx # React dashboard component
└── README.md                    # This file
```

## 🚀 Quick Start Guide

### Prerequisites

- Python 3.9+
- PostgreSQL 14+
- Node.js 18+
- npm or yarn

### Step 1: Set Up Database

```bash
# Create PostgreSQL database
createdb utility_saas

# Run schema migration
psql -d utility_saas -f database_schema.sql
```

### Step 2: Install Backend Dependencies

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install fastapi uvicorn sqlalchemy psycopg2-binary python-dotenv pydantic pandas
```

**Optional ML Libraries:**
```bash
# For Prophet forecasting
pip install prophet

# For XGBoost anomaly detection
pip install xgboost scikit-learn
```

### Step 3: Configure Environment

Create `.env` file in `backend/` directory:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/utility_saas
DEBUG=True
```

### Step 4: Run Backend Server

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- **Base URL**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Step 5: Install Frontend Dependencies

```bash
cd frontend

# Install dependencies
npm install

# Or with yarn
yarn install
```

### Step 6: Run Frontend Development Server

```bash
cd frontend
npm start
```

The dashboard will be available at: http://localhost:3000

## 📡 API Endpoints

### Meter Readings

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/readings/upload` | Upload batch meter readings from smart meters |
| GET | `/api/v1/readings/{meter_id}` | Get readings for a specific meter |

**Example Upload Request:**
```json
POST /api/v1/readings/upload
{
  "readings": [
    {
      "meter_id": "550e8400-e29b-41d4-a716-446655440000",
      "timestamp": "2024-01-15T10:30:00Z",
      "value": 450.5,
      "unit": "kWh",
      "is_manual_entry": false,
      "quality_flag": "valid"
    }
  ]
}
```

### Forecasting

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/forecast/{meter_id}` | Generate 30-day consumption forecast |

**Query Parameters:**
- `days_ahead` (optional): Number of days to forecast (default: 30)

### Anomaly Detection

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/anomalies/detect` | Detect anomalies in consumption patterns |

**Request Body:**
```json
{
  "meter_id": "550e8400-e29b-41d4-a716-446655440000",
  "method": "ensemble",
  "time_range_hours": 24
}
```

**Supported Methods:**
- `zscore` - Statistical Z-score method
- `iqr` - Interquartile Range method
- `moving_average` - Moving average deviation
- `ensemble` - Combined approach (recommended)
- `xgboost` - ML-based detection (requires training)

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/dashboard/{property_id}` | Get comprehensive dashboard data |

### Subsidy Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/subsidy/generate-report` | Generate and submit subsidy report |

**Request Body:**
```json
{
  "anomaly_id": "550e8400-e29b-41d4-a716-446655440000",
  "report_type": "leak_investigation",
  "utility_provider_email": "provider@utility.com"
}
```

### Aggregation (Admin)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/aggregation/hourly` | Trigger hourly aggregation |
| POST | `/api/v1/aggregation/daily` | Trigger daily aggregation |
| POST | `/api/v1/aggregation/monthly` | Trigger monthly aggregation |

## 🤖 Machine Learning Features

### 1. Consumption Forecasting (Prophet)

The forecasting module uses Facebook's Prophet library to predict future electricity consumption:

- **Training Data**: Last 90 days of historical readings
- **Features**: Daily, weekly, and yearly seasonality
- **Output**: 30-day forecast with 95% confidence intervals
- **Accuracy**: Typically achieves MAPE < 15%

```python
from ml_models.forecasting import generate_forecast

result = generate_forecast(
    db=db,
    meter_id="meter-uuid",
    days_ahead=30
)
```

### 2. Anomaly Detection

Multiple detection methods are available:

#### Statistical Methods
- **Z-Score**: Flags values > 2.5 standard deviations from mean
- **IQR**: Uses interquartile range for robust outlier detection
- **Moving Average**: Detects sudden changes from rolling average

#### Ensemble Method (Recommended)
Combines multiple methods; flags anomaly if ≥2 methods agree.

#### XGBoost (Advanced)
ML-based detection trained on labeled historical data:

```python
from ml_models.anomaly_detection import train_xgboost_model

# Train model
train_xgboost_model(
    db=db,
    meter_id="meter-uuid",
    output_path="/models/xgboost_model.json"
)
```

### 3. Subsidy Automation

Automatically generates reports for qualifying anomalies:

**Qualification Criteria:**
- Continuous high consumption over weekend/non-business hours
- Deviation > 100% from expected consumption
- Anomaly type indicates potential leak
- Severity is 'high' or 'critical'

**Output Formats:**
- JSON report with full consumption analysis
- XML report for utility provider systems
- Automatic email/API submission

## 🎨 Frontend Dashboard

The React dashboard provides:

### Summary Cards
- Total consumption (current month)
- Total cost
- Cost savings vs baseline
- Active anomalies count

### Charts
- **Real-time vs Predicted**: Line chart comparing actual consumption with ML predictions
- **30-Day Forecast**: Area chart showing forecast with confidence bands

### Anomaly Management
- List of detected anomalies with severity badges
- One-click resolution
- Subsidy report generation for qualifying anomalies

### Customization
- Filter by utility type (electricity, water, heat)
- Time range selection
- Real-time updates

## 📊 Database Schema

Key tables:

| Table | Description |
|-------|-------------|
| `users` | Platform users (admins, managers) |
| `properties` | Buildings/premises being monitored |
| `meters` | Smart meters with unique IDs |
| `utility_types` | Reference table (electricity, water, heat) |
| `meter_readings` | Time-series consumption data |
| `hourly_summaries` | Aggregated hourly data |
| `daily_summaries` | Aggregated daily data |
| `monthly_summaries` | Aggregated monthly data |
| `anomalies` | Detected anomalies with severity |
| `subsidy_reports` | Generated subsidy applications |

## 🔧 Background Tasks

### Automatic Aggregation

The system automatically aggregates raw readings:

1. **Hourly**: Every hour, aggregates previous hour's readings
2. **Daily**: Every day, aggregates previous day's hourly summaries
3. **Monthly**: Every month, aggregates previous month's daily summaries

### Scheduled Anomaly Detection

Run anomaly detection periodically:

```python
# Example cron job (daily at 2 AM)
0 2 * * * curl -X POST http://localhost:8000/api/v1/anomalies/detect \
  -H "Content-Type: application/json" \
  -d '{"method": "ensemble", "time_range_hours": 24}'
```

## 📝 Example Usage

### Upload Meter Readings

```bash
curl -X POST http://localhost:8000/api/v1/readings/upload \
  -H "Content-Type: application/json" \
  -d '{
    "readings": [
      {
        "meter_id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": "2024-01-15T10:00:00Z",
        "value": 450.5,
        "unit": "kWh"
      },
      {
        "meter_id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": "2024-01-15T11:00:00Z",
        "value": 475.2,
        "unit": "kWh"
      }
    ]
  }'
```

### Get Forecast

```bash
curl http://localhost:8000/api/v1/forecast/550e8400-e29b-41d4-a716-446655440000?days_ahead=30
```

### Detect Anomalies

```bash
curl -X POST http://localhost:8000/api/v1/anomalies/detect \
  -H "Content-Type: application/json" \
  -d '{
    "meter_id": "550e8400-e29b-41d4-a716-446655440000",
    "method": "ensemble",
    "time_range_hours": 24
  }'
```

## 🛠️ Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Verify database exists
psql -l | grep utility_saas
```

### Missing Python Dependencies

```bash
# Reinstall all dependencies
pip install -r backend/requirements.txt
```

### Frontend Build Errors

```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

## 📄 License

MIT License - See LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

## 📞 Support

For issues and questions:
- GitHub Issues: [Create an issue]
- Email: support@utility-monitoring.example.com
