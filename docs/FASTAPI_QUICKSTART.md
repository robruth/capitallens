# FastAPI Migration - Quick Start Guide

## 🎯 Overview

This guide provides the implementation order and key steps for converting the Excel import system to FastAPI + Celery backend.

**Full Plan:** See [FASTAPI_MIGRATION_PLAN.md](./FASTAPI_MIGRATION_PLAN.md) for complete details.

---

## 📋 Implementation Order

### Phase 1: Service Layer (Week 1)
Extract business logic to framework-agnostic services.

```
Priority: HIGH | Complexity: MEDIUM | Risk: LOW
```

**Files to Create:**
- `services/excel_import_service.py` - Refactor [`ExcelImporter`](../scripts/excel_importer.py:309)
- `services/validation_service.py` - Refactor [`ImportValidator`](../scripts/excel_importer.py:937)
- `services/formula_service.py` - Utility functions
- `services/storage_service.py` - File management

**Key Changes:**
- Add `progress_callback` parameter to all service methods
- Return structured dictionaries instead of direct database commits
- Remove CLI-specific code (click, sys.exit)

### Phase 2: Database Schema (Week 1)
Add job tracking tables.

**File to Create:**
- `alembic/versions/002_job_tracking.py`
- `backend/models/job.py` - [`JobRun`](./FASTAPI_MIGRATION_PLAN.md:556), [`JobProgress`](./FASTAPI_MIGRATION_PLAN.md:582)

**Tables:**
- `job_runs` - Track import/validation jobs
- `job_progress` - Detailed progress stages

### Phase 3: Celery Tasks (Week 2)
Background job processing.

**Files to Create:**
- `tasks/celery_app.py` - Celery configuration
- `tasks/import_tasks.py` - [`import_excel_file`](./FASTAPI_MIGRATION_PLAN.md:671)
- `tasks/validation_tasks.py` - Background validation

**Key Features:**
- Redis broker + backend
- Progress tracking via Redis + PostgreSQL
- Error handling with retry logic

### Phase 4: FastAPI Application (Week 2)
REST API implementation.

**Files to Create:**
- `api/main.py` - FastAPI app setup
- `api/config.py` - Configuration management
- `api/dependencies.py` - Dependency injection
- `api/middleware.py` - CORS, logging

**Routers:**
- `api/routers/import.py` - Upload, job status
- `api/routers/models.py` - Model CRUD
- `api/routers/validation.py` - Validation trigger
- `api/routers/websocket.py` - Real-time progress

**Schemas:**
- `api/schemas/import_schema.py`
- `api/schemas/model_schema.py`
- `api/schemas/cell_schema.py`
- `api/schemas/job_schema.py`

### Phase 5: CLI API Client (Week 3)
Modify CLI to support API mode.

**File to Modify:**
- [`scripts/excel_importer.py`](../scripts/excel_importer.py:1) - Add API mode

**Features:**
- `--api-url` flag enables API mode
- WebSocket progress tracking
- Fallback to polling if WebSocket fails
- Maintain backward compatibility

### Phase 6: Docker & Deployment (Week 3-4)
Containerization and deployment.

**Files to Create:**
- `docker/Dockerfile.api`
- `docker/Dockerfile.worker`
- `docker-compose.yml`

---

## 🚀 Quick Commands

### Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start Redis (if not running)
redis-server

# Terminal 1: Start API
uvicorn api.main:app --reload --port 8000

# Terminal 2: Start Celery worker
celery -A tasks.celery_app worker --loglevel=info --concurrency=2

# Terminal 3: Test CLI in API mode
python scripts/excel_importer.py import \
  --file model.xlsx \
  --name "Test Model" \
  --api-url http://localhost:8000
```

### Docker Deployment

```bash
# Build and start all services
docker-compose up --build

# View logs
docker-compose logs -f api
docker-compose logs -f celery_worker

# Stop services
docker-compose down
```

---

## 📊 API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/import/upload` | Upload Excel file |
| GET | `/api/import/job/{job_id}` | Get job status |
| GET | `/api/models` | List models (paginated) |
| GET | `/api/models/{id}` | Get model details |
| GET | `/api/models/{id}/cells` | Get cells (paginated) |
| POST | `/api/models/{id}/validate` | Trigger validation |
| WS | `/ws/import/{job_id}` | Real-time progress |

---

## 🏗️ Architecture Diagram (Simplified)

```
CLI/Browser → FastAPI → Celery → Services → PostgreSQL
                ↓         ↓
              Redis  ←  Progress
                ↓
           WebSocket
```

---

## 🔑 Key Design Decisions

### ✅ Use Celery + Redis
**Reason:** You have Redis running locally, enables robust distributed task queue

### ✅ Store Job Status in PostgreSQL
**Reason:** Simpler, persistent, no additional service needed (Redis only for temp cache)

### ✅ Dual-Mode CLI
**Reason:** Maintains backward compatibility, easy transition

### ✅ Stage-Based Progress
**Reason:** Clear milestones: hashing → parsing → evaluation → insertion

### ✅ Keep Files in models/
**Reason:** Maintain existing behavior, store in temp during upload then move

---

## 📝 Testing Strategy

```python
# Test API endpoint
def test_upload_file(client, sample_excel):
    response = client.post(
        "/api/import/upload",
        files={"file": sample_excel},
        data={"model_name": "Test", "validate": False}
    )
    assert response.status_code == 202
    assert "job_id" in response.json()

# Test WebSocket
async def test_websocket_progress(client, job_id):
    async with client.websocket_connect(f"/ws/import/{job_id}") as ws:
        data = await ws.receive_json()
        assert "progress" in data
```

---

## ⚠️ Critical Considerations

1. **NO Raw Value Copying** - Maintain existing policy: NEVER copy `raw_value` to `calculated_value`
2. **Progress Callbacks** - All service methods must support progress callbacks
3. **Error Handling** - Support partial success (some cells fail, import continues)
4. **File Cleanup** - Remove temporary files after processing
5. **Transaction Management** - Proper commit/rollback in services

---

## 📚 Key Files Reference

| Component | Current | New Location |
|-----------|---------|--------------|
| Excel Import Logic | [`scripts/excel_importer.py`](../scripts/excel_importer.py:309) | `services/excel_import_service.py` |
| Formula Parser | [`scripts/excel_importer.py`](../scripts/excel_importer.py:70) | `services/formula_service.py` |
| Circular Solver | [`scripts/excel_importer.py`](../scripts/excel_importer.py:175) | `services/excel_import_service.py` |
| Database Models | [`backend/models/schema.py`](../backend/models/schema.py:1) | Keep + add `backend/models/job.py` |

---

## 🎯 Success Criteria

- ✅ Existing CLI still works (direct mode)
- ✅ API mode provides same functionality
- ✅ Background jobs complete successfully
- ✅ WebSocket provides real-time updates
- ✅ Error handling is robust
- ✅ Docker deployment works out-of-box
- ✅ Test coverage >80%

---

## 🐛 Debugging Tips

### API not starting?
```bash
# Check dependencies
pip list | grep fastapi

# Check port availability
lsof -i :8000
```

### Celery worker not processing?
```bash
# Check Redis connection
redis-cli ping

# Check Celery tasks
celery -A tasks.celery_app inspect active
```

### WebSocket connection fails?
```bash
# Check if job exists
curl http://localhost:8000/api/import/job/{job_id}

# Test WebSocket with wscat
npm install -g wscat
wscat -c ws://localhost:8000/ws/import/{job_id}
```

---

## 📞 Next Steps

1. **Review** the [full migration plan](./FASTAPI_MIGRATION_PLAN.md)
2. **Approve** the proposed architecture
3. **Start** with Phase 1 (Service Layer)
4. **Test** incrementally after each phase

**Ready to proceed?** Switch to Code mode to begin implementation!

---

**Version:** 1.0  
**Last Updated:** 2025-10-15