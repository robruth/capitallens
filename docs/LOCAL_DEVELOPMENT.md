# Local Development Setup Guide

Complete guide for running the FastAPI backend service locally on macOS.

---

## 📋 Prerequisites

✅ **Already Available:**
- Python 3.10+
- PostgreSQL (local installation)
- Redis (running at redis://localhost:6379)
- Node.js + HyperFormula wrapper

---

## 🚀 Quick Start (5 Minutes)

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your settings

# 3. Run database migrations
alembic upgrade head

# 4. Start services (3 terminals)

# Terminal 1: FastAPI server
uvicorn api.main:app --reload --port 8000

# Terminal 2: Celery worker
celery -A tasks.celery_app worker --loglevel=info --concurrency=2

# Terminal 3: Test upload
curl -X POST "http://localhost:8000/api/import/upload" \
  -F "file=@model.xlsx" \
  -F "model_name=Test Model" \
  -F "validate=false"
```

---

## 📝 Detailed Setup

### Step 1: Install Dependencies

```bash
# Install all Python packages
pip install -r requirements.txt

# Verify installations
python -c "import fastapi; print(f'FastAPI {fastapi.__version__}')"
python -c "import celery; print(f'Celery {celery.__version__}')"
python -c "import redis; print('Redis OK')"
```

**Expected Output:**
```
FastAPI 0.104.1
Celery 5.3.4
Redis OK
```

### Step 2: Configure Environment

Create or update your `.env` file:

```bash
# Copy example
cp .env.example .env

# Edit with your settings
nano .env
```

**Required .env Configuration:**

```bash
# Database Configuration
DATABASE_URL=postgresql://postgres:s3cr3t@localhost/dcmodel

# Redis Configuration  
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=api.log

# Formula Evaluation Settings
TOLERANCE=1e-6
MAX_CIRCULAR_ITERATIONS=100
CONVERGENCE_THRESHOLD=1e-6

# HyperFormula Configuration
HYPERFORMULA_WRAPPER=scripts/hyperformula_wrapper.js

# Storage Configuration
MODELS_DIR=models/
TEMP_UPLOAD_DIR=/tmp/excel_uploads
MAX_FILE_SIZE_MB=100

# API Configuration
API_URL=http://localhost:8000
CORS_ORIGINS=["*"]
ENABLE_API_KEY_AUTH=false
```

### Step 3: Database Setup

```bash
# Verify PostgreSQL is running
psql -l

# Create database if it doesn't exist
createdb dcmodel

# Run migrations
alembic upgrade head

# Verify tables were created
psql dcmodel -c "\dt"
```

**Expected Tables:**
```
 models
 cell
 job_runs          # NEW
 job_progress      # NEW
 alembic_version
```

### Step 4: Verify Redis

```bash
# Check Redis is running
redis-cli ping
# Should return: PONG

# Check Redis database
redis-cli INFO | grep db0
```

### Step 5: Test Service Layer

Before starting the API, test that services work:

```python
# Test script: test_services.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from services.excel_import_service import ExcelImportService

engine = create_engine("postgresql://postgres:password@localhost/dcmodel")
Session = sessionmaker(bind=engine)
session = Session()

def on_progress(stage, percent, message):
    print(f"[{stage}] {percent:.1f}% - {message}")

service = ExcelImportService(session, progress_callback=on_progress)

# Test with a small Excel file
result = service.import_file("test.xlsx", "Test Model", validate=False)
print(f"\nModel ID: {result['model_id']}")
print(f"Stats: {result['stats']}")
```

```bash
python test_services.py
```

---

## 🏃 Running the Application

### Terminal 1: FastAPI Server

```bash
# Development mode (with auto-reload)
uvicorn api.main:app --reload --port 8000 --log-level info

# Production mode (no reload)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Expected Output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**Verify it's running:**
```bash
curl http://localhost:8000/health
```

### Terminal 2: Celery Worker

```bash
# Start worker with 2 concurrent tasks
celery -A tasks.celery_app worker --loglevel=info --concurrency=2

# With auto-reload (development)
watchmedo auto-restart -d . -p '*.py' -- celery -A tasks.celery_app worker --loglevel=info
```

**Expected Output:**
```
[config]
.> app:         capitallens:0x...
.> transport:   redis://localhost:6379/0
.> results:     redis://localhost:6379/0
.> concurrency: 2
.> task events: ON

[queues]
.> default          exchange=default(direct) key=default
.> import           exchange=import(direct) key=import.#
.> validation       exchange=validation(direct) key=validation.#

[tasks]
  . tasks.import_tasks.import_excel_file
  . tasks.validation_tasks.validate_model

[2025-10-15 10:00:00,000: INFO/MainProcess] Connected to redis://localhost:6379/0
[2025-10-15 10:00:00,000: INFO/MainProcess] Ready.
```

**Verify worker is running:**
```bash
celery -A tasks.celery_app inspect active
```

### Terminal 3: Monitor Logs (Optional)

```bash
# Watch API logs
tail -f api.log

# Watch import logs
tail -f import.log

# Watch Celery logs
# Already shown in Terminal 2
```

---

## 🧪 Testing the API

### 1. Health Check

```bash
curl http://localhost:8000/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-15T12:00:00Z",
  "version": "1.0.0",
  "database": "connected",
  "redis": "connected",
  "celery": "active (1 workers)"
}
```

### 2. Upload Excel File

```bash
curl -X POST "http://localhost:8000/api/import/upload" \
  -F "file=@dcmodel_template.xlsx" \
  -F "model_name=DC Model Test" \
  -F "validate=true"
```

**Expected Response:**
```json
{
  "job_id": "abc-123-def-456",
  "message": "Excel import job started",
  "status_url": "/api/import/job/abc-123-def-456",
  "websocket_url": "/ws/import/abc-123-def-456"
}
```

### 3. Check Job Status

```bash
# Using job_id from upload response
curl "http://localhost:8000/api/import/job/abc-123-def-456"
```

**Expected Response (Processing):**
```json
{
  "job_id": "abc-123-def-456",
  "status": "processing",
  "progress": {
    "stage": "evaluation",
    "percent": 65.0,
    "message": "Evaluating formulas..."
  }
}
```

**Expected Response (Complete):**
```json
{
  "job_id": "abc-123-def-456",
  "status": "success",
  "result": {
    "model_id": 123,
    "stats": {
      "total_cells": 758,
      "formula_cells": 617,
      "circular_references": 122
    }
  }
}
```

### 4. List Models

```bash
curl "http://localhost:8000/api/models?page=1&page_size=10"
```

### 5. Get Model Details

```bash
curl "http://localhost:8000/api/models/123"
```

### 6. Get Model Cells

```bash
# All cells
curl "http://localhost:8000/api/models/123/cells"

# Only cells with mismatches
curl "http://localhost:8000/api/models/123/cells?has_mismatch=true"

# Only circular reference cells
curl "http://localhost:8000/api/models/123/cells?is_circular=true"
```

### 7. WebSocket Connection (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/import/abc-123-def-456');

ws.onopen = () => {
    console.log('Connected to progress stream');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(`Progress: ${data.progress?.percent}% - ${data.progress?.message}`);
    
    if (data.status === 'success') {
        console.log('Import complete!', data.result);
        ws.close();
    }
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};
```

### 8. Interactive API Documentation

Open in browser:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

---

## 🐛 Troubleshooting

### Issue: FastAPI won't start

**Error:** `ModuleNotFoundError: No module named 'fastapi'`

**Solution:**
```bash
pip install -r requirements.txt
```

---

**Error:** `sqlalchemy.exc.OperationalError: could not connect to server`

**Solution:**
```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# Start PostgreSQL
brew services start postgresql@15
```

---

### Issue: Celery worker won't start

**Error:** `kombu.exceptions.OperationalError: Connection refused`

**Solution:**
```bash
# Check Redis is running
redis-cli ping

# Start Redis
redis-server

# Or on macOS with Homebrew
brew services start redis
```

---

**Error:** `celery.exceptions.NotRegistered: 'tasks.import_tasks.import_excel_file'`

**Solution:**
```bash
# Make sure you're in the project root directory
cd /Users/robruth/github/capitallens

# Restart worker
celery -A tasks.celery_app worker --loglevel=info
```

---

### Issue: Import fails with file not found

**Error:** Job status shows "failed" with "File not found" error

**Solution:**
```bash
# Ensure temp directory exists
mkdir -p /tmp/excel_uploads

# Check permissions
ls -la /tmp/excel_uploads

# If needed, fix permissions
chmod 755 /tmp/excel_uploads
```

---

### Issue: WebSocket connection fails

**Error:** `WebSocket connection to 'ws://localhost:8000/ws/import/...' failed`

**Solution:**
```bash
# Make sure FastAPI server is running
curl http://localhost:8000/health

# Check if job exists
curl "http://localhost:8000/api/import/job/YOUR_JOB_ID"

# Try using wscat for testing
npm install -g wscat
wscat -c ws://localhost:8000/ws/import/YOUR_JOB_ID
```

---

### Issue: Database migration fails

**Error:** `alembic.util.exc.CommandError: Can't locate revision identified by`

**Solution:**
```bash
# Check current revision
alembic current

# Downgrade and re-upgrade
alembic downgrade base
alembic upgrade head

# Or stamp current version
alembic stamp head
```

---

### Issue: Progress updates not showing

**Solution:**
```bash
# Check Redis connection
redis-cli
> KEYS job_progress:*
> GET job_progress:YOUR_JOB_ID

# Check database progress records
psql dcmodel -c "SELECT * FROM job_progress WHERE job_id = 'YOUR_JOB_ID';"
```

---

## 🧹 Cleanup & Maintenance

### Clear Old Job Records

```bash
# Via Python
python -c "
from tasks.import_tasks import cleanup_old_jobs
result = cleanup_old_jobs.delay(days_to_keep=7)
print(result.get())
"
```

### Clear Redis Cache

```bash
# Clear all progress caches
redis-cli KEYS "job_progress:*" | xargs redis-cli DEL

# Or flush entire database (WARNING: clears everything)
redis-cli FLUSHDB
```

### Clear Temp Files

```bash
# Remove old temp uploads
find /tmp/excel_uploads -type f -mtime +1 -delete

# Or use service
python -c "
from services.storage_service import StorageService
service = StorageService()
deleted = service.cleanup_temp_files('/tmp/excel_uploads', older_than_hours=24)
print(f'Deleted {deleted} temp files')
"
```

---

## 📊 Monitoring

### Check Celery Stats

```bash
# Active tasks
celery -A tasks.celery_app inspect active

# Registered tasks
celery -A tasks.celery_app inspect registered

# Worker stats
celery -A tasks.celery_app inspect stats
```

### Check Database Stats

```sql
-- Total models
SELECT COUNT(*) FROM models;

-- Total cells
SELECT COUNT(*) FROM cell;

-- Job statistics
SELECT job_type, status, COUNT(*) 
FROM job_runs 
GROUP BY job_type, status;

-- Recent jobs
SELECT job_id, job_type, status, created_at, completed_at
FROM job_runs
ORDER BY created_at DESC
LIMIT 10;
```

### Check Redis Stats

```bash
# Redis info
redis-cli INFO stats

# Active job progress caches
redis-cli KEYS "job_progress:*"

# Memory usage
redis-cli INFO memory
```

---

## 🎯 Development Workflow

### Typical Development Session

```bash
# 1. Start services (3 terminals)

# Terminal 1: API server (auto-reload enabled)
uvicorn api.main:app --reload --port 8000

# Terminal 2: Celery worker
celery -A tasks.celery_app worker --loglevel=debug

# Terminal 3: Development/testing
# Make API requests, run tests, etc.

# 2. Make code changes
# FastAPI will auto-reload
# For Celery changes, restart worker (Ctrl+C, then re-run)

# 3. Test changes
curl -X POST "http://localhost:8000/api/import/upload" \
  -F "file=@test.xlsx" \
  -F "model_name=Test"

# 4. Check logs
tail -f api.log
tail -f import.log
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=api --cov=services --cov=tasks

# Run specific test file
pytest tests/test_api/test_import_endpoints.py -v

# Run specific test
pytest tests/test_services/test_excel_import_service.py::test_import_file -v
```

---

## 🔧 Common Development Tasks

### Add New API Endpoint

1. Define Pydantic schema in `api/schemas/`
2. Create endpoint in appropriate router
3. Test with curl or Swagger UI
4. Add test in `tests/test_api/`

### Add New Background Task

1. Define task in `tasks/`
2. Register in `tasks/celery_app.py` includes
3. Add progress callback support
4. Test task execution
5. Add test in `tests/test_tasks/`

### Modify Service Logic

1. Update service in `services/`
2. Service remains framework-agnostic
3. Test service independently
4. No need to restart API or Celery (they use service)

### Database Schema Changes

1. Create Alembic migration:
   ```bash
   alembic revision --autogenerate -m "description"
   ```

2. Review generated migration in `alembic/versions/`

3. Apply migration:
   ```bash
   alembic upgrade head
   ```

4. Update SQLAlchemy models if needed

---

## 📱 API Endpoints Reference

### Import Endpoints

```bash
# Upload file
POST /api/import/upload
  -F "file=@file.xlsx"
  -F "model_name=Model Name"
  -F "validate=true"

# Check job status
GET /api/import/job/{job_id}

# List all jobs
GET /api/import/jobs?page=1&page_size=50

# Cancel job
DELETE /api/import/job/{job_id}
```

### Model Endpoints

```bash
# List models
GET /api/models?page=1&page_size=50&search=financial

# Get model details
GET /api/models/{id}

# Get model cells
GET /api/models/{id}/cells?page=1&has_mismatch=true

# Get cell statistics
GET /api/models/{id}/cells/stats

# Get overall stats
GET /api/models/stats

# Delete model
DELETE /api/models/{id}
```

### Validation Endpoints

```bash
# Trigger validation
POST /api/models/{id}/validate

# Get validation summary (quick)
GET /api/models/{id}/validation/summary

# Get mismatches
GET /api/models/{id}/validation/mismatches?limit=100

# Get NULL calculated cells
GET /api/models/{id}/validation/null-calculated?limit=100
```

### WebSocket Endpoints

```javascript
// Import progress
ws://localhost:8000/ws/import/{job_id}

// Validation progress
ws://localhost:8000/ws/validation/{job_id}
```

### Health Endpoints

```bash
# Health check
GET /health

# Simple ping
GET /api/ping
```

---

## 🌐 Interactive Documentation

Once the server is running, access:

- **Swagger UI:** http://localhost:8000/docs
  - Interactive API documentation
  - Try out endpoints
  - See request/response schemas

- **ReDoc:** http://localhost:8000/redoc
  - Alternative documentation format
  - Better for reading

- **OpenAPI JSON:** http://localhost:8000/openapi.json
  - Raw OpenAPI specification
  - Can import into Postman/Insomnia

---

## 🎓 Next Steps

### 1. Test the API

```bash
# Use the interactive docs
open http://localhost:8000/docs

# Or use curl examples above
```

### 2. Modify CLI for API Mode

The CLI can now use `--api-url` flag:
```bash
# Direct mode (local database)
python scripts/excel_importer.py import \
  --file model.xlsx \
  --name "Model Name"

# API mode (FastAPI backend)
python scripts/excel_importer.py import \
  --file model.xlsx \
  --name "Test" \
  --api-url http://localhost:8000
```

### 3. Monitor Performance

- Check import times
- Monitor Celery worker CPU/memory
- Watch Redis memory usage
- Review database query performance

---

## 💡 Tips & Best Practices

### Development Tips

1. **Use auto-reload** for FastAPI during development
2. **Restart Celery** after task changes (no auto-reload)
3. **Use Swagger UI** for testing endpoints
4. **Check logs** in both api.log and import.log
5. **Use debug mode** to see detailed error traces

### Performance Tips

1. **Adjust worker concurrency** based on CPU cores
2. **Use connection pooling** for database (already configured)
3. **Monitor Redis memory** - clear old progress caches
4. **Clean up old jobs** periodically
5. **Index optimization** - migrations already include indexes

### Security Tips

1. **Enable API key auth** in production (ENABLE_API_KEY_AUTH=true)
2. **Restrict CORS origins** in production
3. **Use HTTPS** in production
4. **Set secure Redis password**
5. **Use environment variables** for secrets

---

## 📞 Getting Help

### Check Logs

```bash
# API server logs
tail -f api.log

# Import process logs
tail -f import.log

# Celery worker logs (in Terminal 2)
```

### Debug Mode

```bash
# Run API in debug mode
DEBUG=true uvicorn api.main:app --reload --log-level debug

# Run Celery in debug mode
celery -A tasks.celery_app worker --loglevel=debug
```

### Verify Setup

```bash
# Run this verification script
python -c "
import sys
print('Python:', sys.version)

import fastapi
print('FastAPI:', fastapi.__version__)

import celery
print('Celery:', celery.__version__)

import redis
r = redis.Redis(host='localhost', port=6379)
print('Redis:', 'Connected' if r.ping() else 'Failed')

from sqlalchemy import create_engine
engine = create_engine('postgresql://localhost/dcmodel')
print('PostgreSQL:', 'Connected' if engine.connect() else 'Failed')

print('\n✅ All systems operational')
"
```

---

## 📚 Additional Resources

- **Full Migration Plan:** [FASTAPI_MIGRATION_PLAN.md](./FASTAPI_MIGRATION_PLAN.md)
- **Architecture Diagrams:** [ARCHITECTURE_DIAGRAMS.md](./ARCHITECTURE_DIAGRAMS.md)
- **Implementation Progress:** [IMPLEMENTATION_PROGRESS.md](./IMPLEMENTATION_PROGRESS.md)
- **Original Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)

---

**Version:** 1.0  
**Last Updated:** 2025-10-15  
**Status:** Ready for Local Development