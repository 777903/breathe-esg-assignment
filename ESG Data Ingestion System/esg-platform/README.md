# ESG Data Ingestion Platform

A production-quality prototype for ingesting, normalising, and reviewing ESG (Environmental, Social, Governance) emissions data from SAP, Utility, and Corporate Travel sources.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  React Frontend (Vite, port 3000)                           │
│  UploadPage ──► UploadForm ──► api.js ──► POST /api/upload/ │
│  DashboardPage ◄── DataTable ◄── useRecords hook            │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP (proxied)
┌───────────────────────────▼─────────────────────────────────┐
│  Django REST Framework (port 8000)                          │
│  api/views.py  (thin — delegates to services)               │
│       │                                                     │
│  services/                                                  │
│    IngestionService ──► adapter.parse() ──► RawData         │
│    NormalizationService ──► unit convert ──► co2e           │
│    ValidationService ──► rule engine ──► status             │
│       │                                                     │
│  adapters/                                                  │
│    SAPAdapter | UtilityAdapter | TravelAdapter              │
│       │                                                     │
│  apps/core/models.py                                        │
│    Organization → DataSource → RawData → EmissionRecord     │
│                                        → ValidationError    │
│                                        → AuditLog           │
└─────────────────────────────────────────────────────────────┘
                            │
                     SQLite (dev)
```

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- pip

### 1. Backend Setup

```bash
cd backend

# Create and activate virtual environment
# On this machine: use python3.11 from Windows Store
"C:\Users\satya\AppData\Local\Microsoft\WindowsApps\python3.11.exe" -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start Django development server
python manage.py runserver
```

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start Vite dev server (proxies /api to localhost:8000)
npm run dev
```

### 3. Initialize Demo Data

Open your browser to [http://localhost:3000](http://localhost:3000), go to the Upload page, and click **"Setup Demo Data"** to create the demo organization and data sources.

Alternatively, call the API directly:
```bash
curl -X POST http://localhost:8000/api/seed/
```

### 4. Ingest Sample Data

1. In the UI: Select a data source → drag a CSV from `backend/sample_data/` → click **Ingest Data**
2. Navigate to **Review Dashboard** to see the results

Or via API:
```bash
# Get data source ID first
curl http://localhost:8000/api/datasources/

# Upload a file
curl -X POST http://localhost:8000/api/upload/ \
  -F "file=@backend/sample_data/sap_fuel_export.csv" \
  -F "data_source_id=<UUID_FROM_ABOVE>"
```

---

## API Documentation

### POST /api/upload/
Upload a CSV file for ingestion.

**Request**: `multipart/form-data`
- `file`: CSV file
- `data_source_id`: UUID of target DataSource

**Response** (201):
```json
{
  "created": 15,
  "valid": 10,
  "suspicious": 3,
  "error": 2,
  "skipped": 0
}
```

---

### GET /api/records/
List emission records with filtering.

**Query params**:
- `source`: `sap` | `utility` | `travel`
- `status`: `valid` | `error` | `suspicious` | `approved` | `pending`
- `scope`: `scope1` | `scope2` | `scope3`
- `page`: page number (default 1)
- `page_size`: records per page (default 50)

**Response** (200):
```json
{
  "count": 42,
  "page": 1,
  "page_size": 50,
  "results": [{ "id": "...", "scope": "scope1", "status": "valid", "co2e_kg": 3312.5, ... }]
}
```

---

### GET /api/records/issues/
Returns all records with status `error` or `suspicious`, including full validation error detail.

---

### GET /api/records/{id}/
Full detail of a single record including `validation_errors` and raw `payload`.

---

### POST /api/records/{id}/approve/
Approve a record (status must not be `error`). Records status → `approved`.

---

### GET /api/dashboard/
Aggregate statistics for the dashboard.

**Response**:
```json
{
  "total_records": 51,
  "total_co2e_kg": 48921.4,
  "status_counts": { "valid": 32, "error": 5, "suspicious": 11, "approved": 3 },
  "source_counts": { "sap": 15, "utility": 12, "travel": 24 },
  "scope_co2e": { "scope1": 12540.2, "scope2": 9821.0, "scope3": 26560.2 },
  "recent_issues": [...],
  "data_sources": [...]
}
```

---

### GET /api/audit/{record_id}/
Full audit trail for a record.

**Response**:
```json
{
  "record_id": "uuid",
  "audit_trail": [
    { "action": "ingested", "actor_name": "System", "changes": {...}, "timestamp": "..." },
    { "action": "approved", "actor_name": "Jane Smith", "changes": {...}, "timestamp": "..." }
  ]
}
```

---

## Project Structure

```
esg-platform/
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── esg_platform/          # Django settings, URLs, WSGI
│   ├── apps/
│   │   └── core/              # Models + Admin
│   │       ├── models.py
│   │       └── admin.py
│   ├── adapters/              # Source-specific parsers
│   │   ├── base.py            # Abstract BaseAdapter
│   │   ├── sap.py             # SAPAdapter
│   │   ├── utility.py         # UtilityAdapter
│   │   └── travel.py          # TravelAdapter
│   ├── services/              # Business logic layer
│   │   ├── ingestion.py       # Orchestrator
│   │   ├── normalization.py   # Unit conversion + CO2e
│   │   └── validation.py      # Rule engine + status
│   ├── api/                   # REST API layer
│   │   ├── serializers.py
│   │   ├── views.py
│   │   └── urls.py
│   └── sample_data/
│       ├── sap_fuel_export.csv
│       ├── utility_electricity.csv
│       └── corporate_travel.csv
│
├── frontend/
│   ├── index.html
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx            # Root + sidebar nav
│       ├── index.css          # Design system
│       ├── main.jsx
│       ├── services/
│       │   └── api.js         # All API calls
│       ├── hooks/
│       │   └── useRecords.js  # Records state management
│       ├── components/
│       │   ├── StatusBadge.jsx
│       │   ├── Filters.jsx
│       │   ├── DataTable.jsx
│       │   └── UploadForm.jsx
│       └── pages/
│           ├── UploadPage.jsx
│           └── DashboardPage.jsx
│
├── MODEL.md        # Schema documentation
├── DECISIONS.md    # Architecture decisions
├── TRADEOFFS.md    # What was not built
├── SOURCES.md      # Real-world data format research
└── README.md       # This file
```

---

## Validation Rules

| Rule Code              | Severity | Applies To    | Triggers When                                   |
|------------------------|----------|---------------|-------------------------------------------------|
| `MISSING_QUANTITY`     | Error    | All           | Quantity is null after parsing                  |
| `NEGATIVE_VALUE`       | Error    | All           | Quantity < 0                                    |
| `MISSING_DATE`         | Error    | All           | Activity date could not be parsed               |
| `FUTURE_DATE`          | Warning  | All           | Date > today + 7 days                           |
| `VERY_OLD_DATE`        | Warning  | All           | Date > 3 years ago                              |
| `EXTREME_VALUE`        | Warning  | All           | Exceeds per-unit threshold                      |
| `MISSING_CO2E`         | Warning  | All           | CO2e null despite quantity being present        |
| `ESTIMATED_READ`       | Warning  | Utility only  | Utility marks read as estimated                 |
| `UNKNOWN_AIRPORT_PAIR` | Warning  | Travel only   | Flight distance could not be resolved from IATA |
| `EXTREME_FLIGHT_DIST`  | Warning  | Travel only   | Distance > 18,000 km (longer than longest route)|

---

## Deployment

### Production Checklist

1. **Settings**: Set `DEBUG=False`, configure `ALLOWED_HOSTS`, change `SECRET_KEY`
2. **Database**: Switch to PostgreSQL in `DATABASES` setting
3. **Static files**: Run `python manage.py collectstatic`, serve via Nginx
4. **Media files**: Use S3 or GCS for uploaded files (configure `DEFAULT_FILE_STORAGE`)
5. **Async**: Add Celery + Redis for background ingestion
6. **Auth**: Add JWT auth and multi-tenant middleware
7. **CORS**: Restrict `CORS_ALLOWED_ORIGINS` to your frontend domain

### Docker (sketch)

```yaml
# docker-compose.yml
services:
  backend:
    build: ./backend
    command: gunicorn esg_platform.wsgi:application --bind 0.0.0.0:8000
    environment:
      - DJANGO_SETTINGS_MODULE=esg_platform.settings
    depends_on: [db]

  frontend:
    build: ./frontend
    command: npm run preview -- --port 3000

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: esg_platform
      POSTGRES_PASSWORD: secret
```

---

## Documentation Index

| File | Contents |
|------|----------|
| [MODEL.md](MODEL.md) | Database schema, ER diagram, normalization pipeline |
| [DECISIONS.md](DECISIONS.md) | Architecture choices and rationale |
| [TRADEOFFS.md](TRADEOFFS.md) | What was skipped and how to add it |
| [SOURCES.md](SOURCES.md) | Real-world data format research, sample data explanation |
