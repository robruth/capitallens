# FastAPI Migration Plan - Excel Import System

## Executive Summary

This document outlines the comprehensive plan to convert the CLI-based Excel import system into a FastAPI backend service with background job processing, while maintaining CLI compatibility.

**Technology Stack:**
- FastAPI (async API framework)
- Celery (distributed task queue)
- Redis (message broker + job status cache)
- WebSocket (real-time progress updates)
- PostgreSQL (persistent storage)

---

## 1. Current Architecture Analysis

### 1.1 Existing Components

**Core Business Logic (scripts/excel_importer.py - 1,056 lines):**
- `FormulaParser` - Parse Excel formulas and extract dependencies
- `CircularReferenceDetector` - Detect circular references using NetworkX
- `CircularSolver` - Iterative solver for circular formulas
- `HyperFormulaEvaluator` - Node.js subprocess interface
- `ExcelImporter` - Main orchestrator (parse, evaluate, insert)
- `ImportValidator` - Post-import validation

**Data Models (backend/models/schema.py):**
- `Model` - Workbook metadata and import summary
- `Cell` - Individual cell data with formulas and calculations

**Current Workflow:**
1. CLI receives file path and model name
2. Compute SHA256 hash (duplicate detection)
3. Copy file to models/ directory
4. Parse workbook (dual load: formulas + values)
5. Build dependency graph
6. Detect circular references
7. Evaluate formulas (non-circular + circular)
8. Bulk insert cells to database
9. Optional: Run validation

**Performance Characteristics:**
- 758 cells: ~3 seconds total
- 10K cells: ~25 seconds (estimated)

### 1.2 Service Boundaries Identification

**Service Layer (Framework-Agnostic):**
- Excel parsing and analysis
- Formula evaluation
- Circular reference solving
- Import validation
- All business logic from ExcelImporter

**API Layer (FastAPI-Specific):**
- Request/response handling
- File upload management
- Job creation and tracking
- WebSocket connections
- Error formatting

**Task Layer (Celery):**
- Background import execution
- Progress tracking
- Result persistence
- Error handling

---

## 2. Proposed Architecture

### 2.1 Directory Structure

```
capitallens/
├── api/
│   ├── __init__.py
│   ├── main.py                      # FastAPI application
│   ├── dependencies.py              # Dependency injection
│   ├── middleware.py                # CORS, logging, etc.
│   ├── config.py                    # Configuration management
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── import.py                # Import endpoints
│   │   ├── models.py                # Model CRUD endpoints
│   │   ├── validation.py            # Validation endpoints
│   │   └── websocket.py             # WebSocket endpoints
│   └── schemas/
│       ├── __init__.py
│       ├── import_schema.py         # Import request/response
│       ├── model_schema.py          # Model schemas
│       ├── cell_schema.py           # Cell schemas
│       ├── job_schema.py            # Job status schemas
│       └── common.py                # Common/shared schemas
├── services/
│   ├── __init__.py
│   ├── excel_import_service.py      # Refactored ExcelImporter
│   ├── validation_service.py        # Refactored ImportValidator
│   ├── formula_service.py           # Formula parsing/evaluation
│   └── storage_service.py           # File storage operations
├── tasks/
│   ├── __init__.py
│   ├── celery_app.py                # Celery configuration
│   ├── import_tasks.py              # Import background tasks
│   └── validation_tasks.py          # Validation background tasks
├── backend/
│   └── models/
│       ├── __init__.py
│       ├── schema.py                # Existing SQLAlchemy models
│       └── job.py                   # New: Job tracking models
├── scripts/
│   ├── excel_importer.py            # Modified: CLI API client
│   └── hyperformula_wrapper.js      # Unchanged
├── tests/
│   ├── test_api/                    # New: API tests
│   ├── test_services/               # New: Service tests
│   ├── test_tasks/                  # New: Task tests
│   └── test_importer.py             # Existing tests
├── docker/
│   ├── Dockerfile.api               # API service container
│   ├── Dockerfile.worker            # Celery worker container
│   └── docker-compose.yml           # Multi-service orchestration
├── alembic/
│   └── versions/
│       ├── 001_initial_schema.py    # Existing
│       └── 002_job_tracking.py      # New: Job tracking tables
└── requirements.txt                 # Updated dependencies
```

### 2.2 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         Clients                              │
├─────────────┬──────────────┬─────────────────┬──────────────┤
│  CLI Tool   │  Web Browser │   External API  │   WebSocket  │
└──────┬──────┴──────┬───────┴────────┬────────┴──────┬───────┘
       │             │                │               │
       │  HTTP/HTTPS │                │               │ WS/WSS
       │             │                │               │
       ▼             ▼                ▼               ▼
┌────────────────────────────────────────────────────────────┐
│              FastAPI Application (api/)                     │
│  ┌──────────┬───────────┬──────────────┬─────────────┐   │
│  │ Import   │  Models   │  Validation  │  WebSocket  │   │
│  │ Router   │  Router   │  Router      │  Handler    │   │
│  └────┬─────┴─────┬─────┴──────┬───────┴──────┬──────┘   │
│       │           │            │              │           │
│       │  ┌────────┴────────────┴──────────────┘           │
│       │  │   Dependency Injection & Middleware            │
│       │  └────────────────────────────────────────┐       │
│       ▼                                            ▼       │
│  ┌──────────────────────┐           ┌──────────────────┐ │
│  │  Job Management      │           │  Response        │ │
│  │  (Create/Track)      │           │  Streaming       │ │
│  └──────────┬───────────┘           └──────────────────┘ │
└─────────────┼─────────────────────────────────────────────┘
              │ Enqueue
              ▼
┌────────────────────────────────────────────────────────────┐
│                   Redis (Message Broker)                    │
│  ┌──────────────────┬────────────────┬──────────────────┐ │
│  │  Task Queue      │  Job Status    │  Progress Cache  │ │
│  └──────────────────┴────────────────┴──────────────────┘ │
└─────────────┬──────────────────────────────────────────────┘
              │ Consume
              ▼
┌────────────────────────────────────────────────────────────┐
│              Celery Workers (tasks/)                        │
│  ┌────────────────────────────────────────────────────┐   │
│  │           Import Task Execution                     │   │
│  │  ┌──────────────────────────────────────────────┐  │   │
│  │  │  1. Receive file from temp storage           │  │   │
│  │  │  2. Invoke ExcelImportService                 │  │   │
│  │  │  3. Update progress (parsing/eval/insert)     │  │   │
│  │  │  4. Handle errors and partial success         │  │   │
│  │  │  5. Store results in PostgreSQL               │  │   │
│  │  └──────────────────────────────────────────────┘  │   │
│  └────────────────────────────────────────────────────┘   │
└─────────────┬──────────────────────────────────────────────┘
              │ Uses
              ▼
┌────────────────────────────────────────────────────────────┐
│           Services Layer (Framework-Agnostic)               │
│  ┌──────────────┬─────────────────┬────────────────────┐  │
│  │  Excel       │  Validation     │  Formula           │  │
│  │  Import      │  Service        │  Service           │  │
│  │  Service     │                 │                    │  │
│  └──────┬───────┴────────┬────────┴──────┬─────────────┘  │
└─────────┼────────────────┼───────────────┼────────────────┘
          │ Reads/Writes   │               │
          ▼                ▼               ▼
┌────────────────────────────────────────────────────────────┐
│                      PostgreSQL                             │
│  ┌──────────┬──────────┬────────────┬──────────────────┐  │
│  │  models  │   cell   │  job_runs  │  job_progress    │  │
│  └──────────┴──────────┴────────────┴──────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

---

## 3. Service Layer Design

### 3.1 Excel Import Service

**File:** `services/excel_import_service.py`

**Responsibilities:**
- Parse Excel workbooks
- Build dependency graphs
- Evaluate formulas
- Handle circular references
- Bulk insert cells

**Key Changes from Current Implementation:**
```python
class ExcelImportService:
    """Framework-agnostic Excel import service."""
    
    def __init__(self, db_session: Session, progress_callback=None):
        """
        Args:
            db_session: SQLAlchemy session
            progress_callback: Optional callback for progress updates
                              Signature: callback(stage: str, percent: float, message: str)
        """
        self.session = db_session
        self.progress_callback = progress_callback or (lambda *args: None)
        
        # Keep existing components
        self.hf_evaluator = HyperFormulaEvaluator()
        self.parser = FormulaParser()
        self.circular_detector = CircularReferenceDetector()
        self.circular_solver = CircularSolver()
        self.stats = {}
    
    def import_file(self, file_path: str, model_name: str, 
                   validate: bool = False) -> Dict[str, Any]:
        """
        Import Excel file and return detailed results.
        
        Returns:
            {
                'model_id': int,
                'stats': {...},
                'validation_results': {...} if validate else None,
                'errors': [...] if any
            }
        """
        self._emit_progress('hashing', 5, 'Computing file hash...')
        file_hash = self.compute_file_hash(file_path)
        
        self._emit_progress('parsing', 10, 'Parsing workbook...')
        workbook_data = self.parse_workbook(file_path)
        
        self._emit_progress('dependencies', 30, 'Building dependency graph...')
        self._build_dependency_graph(workbook_data)
        
        self._emit_progress('evaluation', 50, 'Evaluating formulas...')
        self.evaluate_formulas(workbook_data['cells'])
        
        self._emit_progress('insertion', 80, 'Inserting cells...')
        model_id = self._create_model_and_cells(...)
        
        self._emit_progress('complete', 100, 'Import complete')
        
        return {
            'model_id': model_id,
            'stats': self.stats,
            'validation_results': validation_results if validate else None
        }
    
    def _emit_progress(self, stage: str, percent: float, message: str):
        """Emit progress update via callback."""
        self.progress_callback(stage, percent, message)
```

**Progress Stages:**
1. `hashing` (5%) - Computing file hash
2. `parsing` (10-30%) - Parsing workbook structure
3. `dependencies` (30-40%) - Building dependency graph
4. `evaluation` (40-80%) - Evaluating formulas
5. `insertion` (80-95%) - Database insertion
6. `validation` (95-99%) - Optional validation
7. `complete` (100%) - Job finished

### 3.2 Validation Service

**File:** `services/validation_service.py`

```python
class ValidationService:
    """Framework-agnostic validation service."""
    
    def __init__(self, db_session: Session, progress_callback=None):
        self.session = db_session
        self.progress_callback = progress_callback or (lambda *args: None)
    
    def validate_model(self, model_id: int) -> Dict[str, Any]:
        """
        Validate all formulas in a model.
        
        Returns validation report with matches, mismatches, errors.
        """
        # Implementation from ImportValidator
        pass
```

### 3.3 Formula Service

**File:** `services/formula_service.py`

```python
class FormulaService:
    """Formula parsing and evaluation utilities."""
    
    @staticmethod
    def parse_dependencies(formula: str, current_sheet: str) -> List[str]:
        """Extract cell dependencies from formula."""
        parser = FormulaParser()
        return parser.extract_dependencies(formula, current_sheet)
    
    @staticmethod
    def is_text_formula(formula: str) -> bool:
        """Check if formula returns text."""
        parser = FormulaParser()
        return parser.is_text_formula(formula)
```

---

## 4. Celery Task Architecture

### 4.1 Celery Configuration

**File:** `tasks/celery_app.py`

```python
from celery import Celery
from api.config import settings

celery_app = Celery(
    'capitallens',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=['tasks.import_tasks', 'tasks.validation_tasks']
)

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 minutes
    task_soft_time_limit=1500,  # 25 minutes
    worker_prefetch_multiplier=1,
    result_expires=3600,  # 1 hour
)
```

### 4.2 Import Task

**File:** `tasks/import_tasks.py`

```python
from celery import Task
from tasks.celery_app import celery_app
from services.excel_import_service import ExcelImportService
from backend.models.job import JobRun, JobStatus
from sqlalchemy.orm import sessionmaker

class ImportTask(Task):
    """Base task with progress tracking."""
    
    def on_progress(self, stage: str, percent: float, message: str):
        """Update job progress in Redis and database."""
        job_id = self.request.id
        
        # Store in Redis for real-time WebSocket updates
        redis_client.setex(
            f'job_progress:{job_id}',
            3600,  # 1 hour expiry
            json.dumps({
                'stage': stage,
                'percent': percent,
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            })
        )
        
        # Update database progress record
        with get_db_session() as session:
            progress = JobProgress(
                job_id=job_id,
                stage=stage,
                percent=percent,
                message=message
            )
            session.add(progress)
            session.commit()

@celery_app.task(base=ImportTask, bind=True)
def import_excel_file(self, file_path: str, model_name: str, 
                     validate: bool = False) -> Dict[str, Any]:
    """
    Background task to import Excel file.
    
    Args:
        file_path: Path to uploaded Excel file
        model_name: User-provided model name
        validate: Whether to run post-import validation
    
    Returns:
        Import results dictionary
    """
    job_id = self.request.id
    
    try:
        # Update job status to PROCESSING
        with get_db_session() as session:
            job_run = session.query(JobRun).filter_by(job_id=job_id).first()
            if job_run:
                job_run.status = JobStatus.PROCESSING
                job_run.started_at = datetime.utcnow()
                session.commit()
        
        # Execute import with progress callback
        with get_db_session() as session:
            service = ExcelImportService(
                db_session=session,
                progress_callback=self.on_progress
            )
            
            result = service.import_file(
                file_path=file_path,
                model_name=model_name,
                validate=validate
            )
        
        # Update job status to SUCCESS
        with get_db_session() as session:
            job_run = session.query(JobRun).filter_by(job_id=job_id).first()
            if job_run:
                job_run.status = JobStatus.SUCCESS
                job_run.completed_at = datetime.utcnow()
                job_run.result = result
                session.commit()
        
        # Clean up temporary file
        if file_path.startswith('/tmp/'):
            os.remove(file_path)
        
        return result
        
    except Exception as e:
        # Update job status to FAILED
        error_details = {
            'error': str(e),
            'traceback': traceback.format_exc()
        }
        
        with get_db_session() as session:
            job_run = session.query(JobRun).filter_by(job_id=job_id).first()
            if job_run:
                job_run.status = JobStatus.FAILED
                job_run.completed_at = datetime.utcnow()
                job_run.error = error_details
                session.commit()
        
        # Re-raise for Celery to handle
        raise
```

---

## 5. Database Schema Extensions

### 5.1 Job Tracking Tables

**File:** `alembic/versions/002_job_tracking.py`

```sql
-- Job runs table
CREATE TABLE job_runs (
    job_id VARCHAR(255) PRIMARY KEY,           -- Celery task ID
    job_type VARCHAR(50) NOT NULL,             -- 'import', 'validation'
    status VARCHAR(20) NOT NULL,               -- 'pending', 'processing', 'success', 'failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- Job parameters
    params JSONB NOT NULL DEFAULT '{}',
    
    -- Results
    result JSONB,
    error JSONB,
    
    -- Associated model (if applicable)
    model_id INTEGER REFERENCES models(id) ON DELETE SET NULL,
    
    -- Metadata
    created_by VARCHAR(255),                   -- User/API key
    
    CHECK (status IN ('pending', 'processing', 'success', 'failed', 'cancelled'))
);

CREATE INDEX idx_job_runs_status ON job_runs(status);
CREATE INDEX idx_job_runs_created_at ON job_runs(created_at);
CREATE INDEX idx_job_runs_model_id ON job_runs(model_id);

-- Job progress tracking (detailed progress stages)
CREATE TABLE job_progress (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL REFERENCES job_runs(job_id) ON DELETE CASCADE,
    stage VARCHAR(50) NOT NULL,                -- 'parsing', 'evaluation', etc.
    percent NUMERIC(5,2) NOT NULL,             -- 0.00 to 100.00
    message TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_job_progress_job_id ON job_progress(job_id);
CREATE INDEX idx_job_progress_timestamp ON job_progress(timestamp);
```

**SQLAlchemy Models:**

**File:** `backend/models/job.py`

```python
from enum import Enum
from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from backend.models.schema import Base

class JobStatus(str, Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    SUCCESS = 'success'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

class JobType(str, Enum):
    IMPORT = 'import'
    VALIDATION = 'validation'

class JobRun(Base):
    __tablename__ = 'job_runs'
    
    job_id = Column(String(255), primary_key=True)
    job_type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default=JobStatus.PENDING)
    created_at = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    started_at = Column(TIMESTAMP, nullable=True)
    completed_at = Column(TIMESTAMP, nullable=True)
    
    params = Column(JSONB, nullable=False, default={})
    result = Column(JSONB, nullable=True)
    error = Column(JSONB, nullable=True)
    
    model_id = Column(Integer, ForeignKey('models.id', ondelete='SET NULL'), nullable=True)
    created_by = Column(String(255), nullable=True)
    
    # Relationships
    model = relationship('Model', back_populates='jobs')
    progress = relationship('JobProgress', back_populates='job', cascade='all, delete-orphan')

class JobProgress(Base):
    __tablename__ = 'job_progress'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(255), ForeignKey('job_runs.job_id', ondelete='CASCADE'), nullable=False)
    stage = Column(String(50), nullable=False)
    percent = Column(Numeric(5, 2), nullable=False)
    message = Column(Text, nullable=True)
    timestamp = Column(TIMESTAMP, server_default=text('CURRENT_TIMESTAMP'))
    
    # Relationships
    job = relationship('JobRun', back_populates='progress')
```

---

## 6. API Design

### 6.1 Pydantic Schemas

**File:** `api/schemas/import_schema.py`

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

class ImportRequest(BaseModel):
    """Request schema for file import."""
    model_name: str = Field(..., min_length=1, max_length=255, description="User-friendly model name")
    validate: bool = Field(False, description="Run post-import validation")

class JobStatusEnum(str, Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    SUCCESS = 'success'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

class JobProgressResponse(BaseModel):
    """Real-time progress update."""
    stage: str
    percent: float = Field(..., ge=0, le=100)
    message: str
    timestamp: datetime

class JobStatusResponse(BaseModel):
    """Job status response."""
    job_id: str
    job_type: str
    status: JobStatusEnum
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: Optional[JobProgressResponse] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

class ImportStartResponse(BaseModel):
    """Response when import is initiated."""
    job_id: str
    message: str = "Import job started"
    status_url: str
    websocket_url: str
```

**File:** `api/schemas/model_schema.py`

```python
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

class ModelListItem(BaseModel):
    """Model list item."""
    id: int
    name: str
    original_filename: Optional[str]
    file_hash: str
    uploaded_at: datetime
    workbook_metadata: Dict[str, Any]
    
    class Config:
        from_attributes = True

class ModelDetail(ModelListItem):
    """Detailed model information."""
    import_summary: Dict[str, Any]
    updated_at: datetime

class ModelListResponse(BaseModel):
    """Paginated model list."""
    total: int
    page: int
    page_size: int
    items: List[ModelListItem]
```

**File:** `api/schemas/cell_schema.py`

```python
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal

class CellResponse(BaseModel):
    """Cell data response."""
    sheet_name: str
    cell: str
    row_num: int
    col_letter: str
    cell_type: str
    raw_value: Optional[Decimal]
    raw_text: Optional[str]
    formula: Optional[str]
    calculated_value: Optional[Decimal]
    calculated_text: Optional[str]
    is_circular: bool
    has_mismatch: bool
    
    class Config:
        from_attributes = True

class CellListResponse(BaseModel):
    """Paginated cell list."""
    total: int
    page: int
    page_size: int
    items: List[CellResponse]
```

### 6.2 API Endpoints

**File:** `api/routers/import.py`

```python
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from api.dependencies import get_db
from api.schemas.import_schema import ImportRequest, ImportStartResponse, JobStatusResponse
from backend.models.job import JobRun, JobType, JobStatus
from tasks.import_tasks import import_excel_file
import tempfile
import shutil

router = APIRouter(prefix='/api/import', tags=['import'])

@router.post('/upload', response_model=ImportStartResponse, status_code=202)
async def upload_excel_file(
    file: UploadFile = File(..., description="Excel file to import"),
    model_name: str = Form(...),
    validate: bool = Form(False),
    db: Session = Depends(get_db)
):
    """
    Upload Excel file and start import job.
    
    Returns immediately with job ID for tracking progress.
    """
    # Validate file type
    if not file.filename.endswith(('.xlsx', '.xlsm')):
        raise HTTPException(
            status_code=400,
            detail="Only .xlsx and .xlsm files are supported"
        )
    
    # Save to temporary location
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    try:
        shutil.copyfileobj(file.file, temp_file)
        temp_file.close()
        
        # Create job record
        job_run = JobRun(
            job_id=None,  # Will be set by Celery
            job_type=JobType.IMPORT,
            status=JobStatus.PENDING,
            params={
                'filename': file.filename,
                'model_name': model_name,
                'validate': validate
            }
        )
        db.add(job_run)
        db.flush()
        
        # Start Celery task
        task = import_excel_file.apply_async(
            args=[temp_file.name, model_name, validate]
        )
        
        # Update job_id
        job_run.job_id = task.id
        db.commit()
        
        return ImportStartResponse(
            job_id=task.id,
            status_url=f"/api/import/job/{task.id}",
            websocket_url=f"/ws/import/{task.id}"
        )
        
    except Exception as e:
        if temp_file:
            os.unlink(temp_file.name)
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/job/{job_id}', response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Get current status of import job.
    """
    job_run = db.query(JobRun).filter_by(job_id=job_id).first()
    if not job_run:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get latest progress from Redis
    progress_data = redis_client.get(f'job_progress:{job_id}')
    progress = None
    if progress_data:
        progress = JobProgressResponse(**json.loads(progress_data))
    
    return JobStatusResponse(
        job_id=job_run.job_id,
        job_type=job_run.job_type,
        status=job_run.status,
        created_at=job_run.created_at,
        started_at=job_run.started_at,
        completed_at=job_run.completed_at,
        progress=progress,
        result=job_run.result,
        error=job_run.error
    )
```

**File:** `api/routers/models.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from api.dependencies import get_db
from api.schemas.model_schema import ModelListResponse, ModelDetail
from backend.models.schema import Model

router = APIRouter(prefix='/api/models', tags=['models'])

@router.get('', response_model=ModelListResponse)
async def list_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List all imported models with pagination."""
    total = db.query(Model).count()
    models = db.query(Model).order_by(Model.uploaded_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    return ModelListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=models
    )

@router.get('/{model_id}', response_model=ModelDetail)
async def get_model(
    model_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed information about a model."""
    model = db.query(Model).filter_by(id=model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model

@router.get('/{model_id}/cells', response_model=CellListResponse)
async def get_model_cells(
    model_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    sheet_name: Optional[str] = Query(None),
    has_formula: Optional[bool] = Query(None),
    has_mismatch: Optional[bool] = Query(None),
    db: Session = Depends(get_db)
):
    """Get cells for a model with filtering and pagination."""
    query = db.query(Cell).filter_by(model_id=model_id)
    
    if sheet_name:
        query = query.filter_by(sheet_name=sheet_name)
    if has_formula is not None:
        query = query.filter(Cell.formula.isnot(None) if has_formula else Cell.formula.is_(None))
    if has_mismatch is not None:
        query = query.filter_by(has_mismatch=has_mismatch)
    
    total = query.count()
    cells = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return CellListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=cells
    )
```

**File:** `api/routers/validation.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies import get_db
from tasks.validation_tasks import validate_model_task
from backend.models.job import JobRun, JobType, JobStatus

router = APIRouter(prefix='/api/models', tags=['validation'])

@router.post('/{model_id}/validate', response_model=ImportStartResponse, status_code=202)
async def trigger_validation(
    model_id: int,
    db: Session = Depends(get_db)
):
    """
    Trigger post-import validation for a model.
    
    Returns job ID for tracking progress.
    """
    # Check model exists
    model = db.query(Model).filter_by(id=model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Create job record
    job_run = JobRun(
        job_type=JobType.VALIDATION,
        status=JobStatus.PENDING,
        model_id=model_id,
        params={'model_id': model_id}
    )
    db.add(job_run)
    db.flush()
    
    # Start Celery task
    task = validate_model_task.apply_async(args=[model_id])
    
    job_run.job_id = task.id
    db.commit()
    
    return ImportStartResponse(
        job_id=task.id,
        status_url=f"/api/import/job/{task.id}",
        websocket_url=f"/ws/import/{task.id}"
    )
```

### 6.3 WebSocket Implementation

**File:** `api/routers/websocket.py`

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from api.dependencies import get_db
import asyncio
import json
import redis

router = APIRouter()

redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

@router.websocket('/ws/import/{job_id}')
async def websocket_import_progress(
    websocket: WebSocket,
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time import progress updates.
    
    Sends progress updates every time the job updates its status.
    """
    await websocket.accept()
    
    try:
        # Verify job exists
        job_run = db.query(JobRun).filter_by(job_id=job_id).first()
        if not job_run:
            await websocket.send_json({
                'error': 'Job not found',
                'job_id': job_id
            })
            await websocket.close()
            return
        
        last_progress = None
        
        while True:
            # Check if job is complete
            db.refresh(job_run)
            
            # Get current progress from Redis
            progress_data = redis_client.get(f'job_progress:{job_id}')
            
            if progress_data:
                progress = json.loads(progress_data)
                
                # Only send if progress changed
                if progress != last_progress:
                    await websocket.send_json({
                        'job_id': job_id,
                        'status': job_run.status,
                        'progress': progress
                    })
                    last_progress = progress
            
            # Send final status if complete
            if job_run.status in [JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED]:
                await websocket.send_json({
                    'job_id': job_id,
                    'status': job_run.status,
                    'completed_at': job_run.completed_at.isoformat() if job_run.completed_at else None,
                    'result': job_run.result,
                    'error': job_run.error
                })
                break
            
            # Wait before checking again
            await asyncio.sleep(0.5)  # Check every 500ms
        
        await websocket.close()
        
    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({
            'error': str(e)
        })
        await websocket.close()
```

---

## 7. CLI to API Conversion

### 7.1 Modified CLI Tool

**File:** `scripts/excel_importer.py`

```python
#!/usr/bin/env python3
"""
Excel to PostgreSQL Import CLI - API Client Mode

This script can now operate in two modes:
1. Direct mode (default): Direct database import (legacy behavior)
2. API mode: Makes HTTP requests to FastAPI backend

Usage:
    # Direct mode (unchanged)
    python scripts/excel_importer.py import --file model.xlsx --name "Model Name"
    
    # API mode
    python scripts/excel_importer.py import --file model.xlsx --name "Model Name" --api-url http://localhost:8000
"""

import click
import requests
from pathlib import Path
import time
import sys
from websocket import create_connection
import json

# Keep all existing classes and functionality...

@click.group()
@click.option('--api-url', envvar='API_URL', help='FastAPI backend URL (enables API mode)')
@click.pass_context
def cli(ctx, api_url):
    """Excel to PostgreSQL Import CLI"""
    ctx.ensure_object(dict)
    ctx.obj['api_url'] = api_url
    ctx.obj['mode'] = 'api' if api_url else 'direct'

@cli.command()
@click.option('--file', '-f', required=True, type=click.Path(exists=True))
@click.option('--name', '-n', required=True)
@click.option('--validate', is_flag=True)
@click.pass_context
def import_cmd(ctx, file: str, name: str, validate: bool):
    """Import an Excel workbook."""
    
    if ctx.obj['mode'] == 'api':
        # API mode: Upload via HTTP
        import_via_api(ctx.obj['api_url'], file, name, validate)
    else:
        # Direct mode: Use existing logic
        import_direct(file, name, validate)

def import_via_api(api_url: str, file_path: str, model_name: str, validate: bool):
    """Import file via FastAPI backend."""
    
    click.echo(f"📤 Uploading {file_path} to {api_url}...")
    
    # Upload file
    with open(file_path, 'rb') as f:
        files = {'file': (Path(file_path).name, f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        data = {
            'model_name': model_name,
            'validate': validate
        }
        
        response = requests.post(
            f"{api_url}/api/import/upload",
            files=files,
            data=data,
            timeout=30
        )
    
    if response.status_code != 202:
        click.echo(f"❌ Upload failed: {response.text}", err=True)
        sys.exit(1)
    
    result = response.json()
    job_id = result['job_id']
    
    click.echo(f"✓ Upload successful. Job ID: {job_id}")
    click.echo("🔄 Tracking progress via WebSocket...\n")
    
    # Connect to WebSocket for real-time progress
    ws_url = f"{api_url.replace('http://', 'ws://').replace('https://', 'wss://')}/ws/import/{job_id}"
    
    try:
        ws = create_connection(ws_url)
        
        while True:
            message = ws.recv()
            data = json.loads(message)
            
            if 'error' in data:
                click.echo(f"❌ Error: {data['error']}", err=True)
                break
            
            if 'progress' in data:
                progress = data['progress']
                stage = progress['stage']
                percent = progress['percent']
                message = progress['message']
                
                # Show progress bar
                bar_length = 40
                filled = int(bar_length * percent / 100)
                bar = '█' * filled + '░' * (bar_length - filled)
                
                click.echo(f"\r[{bar}] {percent:.1f}% - {stage}: {message}", nl=False)
            
            if data.get('status') in ['success', 'failed', 'cancelled']:
                click.echo()  # New line after progress bar
                
                if data['status'] == 'success':
                    result = data.get('result', {})
                    click.echo("\n✓ Import successful!")
                    click.echo(f"Model ID: {result.get('model_id')}")
                    
                    stats = result.get('stats', {})
                    if stats:
                        click.echo("\nStatistics:")
                        click.echo(f"  Total cells: {stats.get('total_cells', 0)}")
                        click.echo(f"  Formula cells: {stats.get('formula_cells', 0)}")
                        click.echo(f"  Circular references: {stats.get('circular_references', 0)}")
                else:
                    error = data.get('error', {})
                    click.echo(f"\n❌ Import failed: {error.get('error', 'Unknown error')}", err=True)
                
                break
        
        ws.close()
        
    except Exception as e:
        click.echo(f"\n❌ WebSocket error: {e}", err=True)
        
        # Fall back to polling
        click.echo("⏱️  Falling back to status polling...")
        poll_job_status(api_url, job_id)

def poll_job_status(api_url: str, job_id: str):
    """Poll job status via REST API."""
    while True:
        try:
            response = requests.get(f"{api_url}/api/import/job/{job_id}")
            if response.status_code == 200:
                data = response.json()
                
                status = data['status']
                progress = data.get('progress')
                
                if progress:
                    click.echo(f"\r{progress['stage']}: {progress['message']} ({progress['percent']:.1f}%)", nl=False)
                
                if status in ['success', 'failed', 'cancelled']:
                    click.echo()
                    
                    if status == 'success':
                        click.echo("✓ Import successful!")
                        result = data.get('result', {})
                        click.echo(f"Model ID: {result.get('model_id')}")
                    else:
                        click.echo(f"❌ Import {status}", err=True)
                    
                    break
            
            time.sleep(2)
            
        except Exception as e:
            click.echo(f"\n❌ Error checking status: {e}", err=True)
            sys.exit(1)

def import_direct(file_path: str, model_name: str, validate: bool):
    """Original direct import logic (unchanged)."""
    # Keep existing implementation
    pass
```

---

## 8. Configuration Management

**File:** `api/config.py`

```python
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings."""
    
    # API
    API_TITLE: str = "Capital Lens Excel Import API"
    API_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    
    # Database
    DATABASE_URL: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # File Storage
    MODELS_DIR: str = "models/"
    TEMP_UPLOAD_DIR: str = "/tmp/excel_uploads"
    MAX_FILE_SIZE_MB: int = 100
    
    # Formula Evaluation
    TOLERANCE: float = 1e-6
    MAX_CIRCULAR_ITERATIONS: int = 100
    CONVERGENCE_THRESHOLD: float = 1e-6
    HYPERFORMULA_WRAPPER: str = "scripts/hyperformula_wrapper.js"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "import.log"
    
    # CORS
    CORS_ORIGINS: list = ["*"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

---

## 9. Docker Deployment

### 9.1 Multi-Service Docker Compose

**File:** `docker-compose.yml`

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: dcmodel
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: s3cr3t
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://postgres:s3cr3t@postgres/dcmodel
      REDIS_URL: redis://redis:6379/0
      LOG_LEVEL: INFO
    volumes:
      - ./models:/app/models
      - ./scripts:/app/scripts
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

  celery_worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    environment:
      DATABASE_URL: postgresql://postgres:s3cr3t@postgres/dcmodel
      REDIS_URL: redis://redis:6379/0
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/0
    volumes:
      - ./models:/app/models
      - ./scripts:/app/scripts
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: celery -A tasks.celery_app worker --loglevel=info --concurrency=2

volumes:
  postgres_data:
```

### 9.2 API Dockerfile

**File:** `docker/Dockerfile.api`

```dockerfile
FROM python:3.10-slim

# Install Node.js for HyperFormula
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g hyperformula && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p models/ /tmp/excel_uploads

# Expose port
EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 9.3 Worker Dockerfile

**File:** `docker/Dockerfile.worker`

```dockerfile
FROM python:3.10-slim

# Install Node.js for HyperFormula
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g hyperformula && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p models/ /tmp/excel_uploads

CMD ["celery", "-A", "tasks.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
```

---

## 10. Updated Requirements

**File:** `requirements.txt`

```txt
# Core dependencies
SQLAlchemy>=2.0.0
alembic>=1.12.0
psycopg2-binary>=2.9.9
python-dotenv>=1.0.0

# FastAPI and web framework
fastapi>=0.104.1
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6
websockets>=12.0

# Pydantic for validation
pydantic>=2.5.0
pydantic-settings>=2.1.0

# Celery and Redis
celery>=5.3.4
redis>=5.0.1

# Excel parsing and evaluation
openpyxl>=3.1.2

# CLI
click>=8.1.7
requests>=2.31.0
websocket-client>=1.6.4

# Testing
pytest>=7.4.3
pytest-cov>=4.1.0
pytest-asyncio>=0.21.1
httpx>=0.25.2

# Utilities
networkx>=3.2.1
```

---

## 11. Error Handling Strategy

### 11.1 Error Categories

1. **Upload Errors**
   - Invalid file type
   - File too large
   - Corrupted Excel file
   - **Response:** 400 Bad Request with details

2. **Processing Errors**
   - Formula evaluation failures
   - Circular reference convergence issues
   - Database constraint violations
   - **Response:** Job status = FAILED with error details

3. **Partial Success**
   - Some cells failed to evaluate
   - Some formulas have mismatches
   - **Strategy:** Complete import, store NULL for failed cells, report in result

### 11.2 Error Response Format

```python
class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    path: Optional[str] = None
```

### 11.3 Partial Success Handling

```python
# In ImportTask
result = {
    'model_id': model_id,
    'stats': stats,
    'status': 'partial_success' if errors else 'success',
    'errors': [
        {
            'cell': 'Sheet1!A1',
            'error': 'Formula evaluation failed',
            'formula': '=INVALID(A1)'
        }
    ],
    'warnings': [
        {
            'cell': 'Sheet1!B2',
            'warning': 'Mismatch detected',
            'expected': 100.0,
            'actual': 100.01
        }
    ]
}
```

---

## 12. Security Considerations

### 12.1 API Authentication

**Implementation Plan:**
- Use API Keys for programmatic access
- Optional: JWT tokens for user authentication
- Store API keys in database with rate limiting

```python
# api/dependencies.py
async def get_api_key(api_key: str = Header(..., alias="X-API-Key")):
    """Validate API key."""
    # Check against database
    pass
```

### 12.2 File Upload Security

- Validate file type (magic bytes, not just extension)
- Enforce file size limits (100MB default)
- Scan for macros (warn but don't execute)
- Store files with hash-based names

### 12.3 Rate Limiting

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post('/upload')
@limiter.limit("5/minute")  # 5 uploads per minute
async def upload_excel_file(...):
    pass
```

---

## 13. Testing Strategy

### 13.1 Test Categories

1. **Unit Tests**
   - Service layer methods
   - Formula parsing
   - Circular solver

2. **Integration Tests**
   - API endpoints
   - Database operations
   - Celery tasks

3. **E2E Tests**
   - Full import workflow
   - WebSocket progress tracking
   - CLI API client

### 13.2 Test Structure

```
tests/
├── test_api/
│   ├── test_import_endpoints.py
│   ├── test_model_endpoints.py
│   └── test_websocket.py
├── test_services/
│   ├── test_excel_import_service.py
│   └── test_validation_service.py
├── test_tasks/
│   ├── test_import_tasks.py
│   └── test_celery_config.py
└── fixtures/
    ├── sample_models/
    └── conftest.py
```

---

## 14. Migration Path

### 14.1 Phase 1: Service Layer Refactoring (Week 1)

1. Extract business logic to `services/`
2. Add progress callback support
3. Update tests for services
4. Keep CLI working with new services

### 14.2 Phase 2: API & Task Implementation (Week 2)

1. Create FastAPI application structure
2. Implement Pydantic schemas
3. Implement API endpoints
4. Create Celery tasks
5. Add job tracking tables

### 14.3 Phase 3: WebSocket & CLI Client (Week 3)

1. Implement WebSocket progress
2. Modify CLI to support API mode
3. Add Docker containers
4. End-to-end testing

### 14.4 Phase 4: Production Readiness (Week 4)

1. Add authentication
2. Performance optimization
3. Monitoring and logging
4. Documentation
5. Deployment automation

---

## 15. Success Metrics

- **Backward Compatibility:** Existing CLI still works
- **API Response Time:** Upload endpoint < 500ms
- **Job Processing:** Same performance as CLI (3s for 758 cells)
- **WebSocket Latency:** Progress updates within 1 second
- **Error Recovery:** Graceful handling of failures
- **Test Coverage:** >80% for new code

---

## Appendix A: Example API Usage

### Upload File via cURL

```bash
curl -X POST "http://localhost:8000/api/import/upload" \
  -H "X-API-Key: your-api-key" \
  -F "file=@dcmodel.xlsx" \
  -F "model_name=DC Model Test" \
  -F "validate=true"

# Response:
{
  "job_id": "abc-123-def-456",
  "message": "Import job started",
  "status_url": "/api/import/job/abc-123-def-456",
  "websocket_url": "/ws/import/abc-123-def-456"
}
```

### Check Job Status

```bash
curl "http://localhost:8000/api/import/job/abc-123-def-456" \
  -H "X-API-Key: your-api-key"

# Response:
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

### WebSocket Connection (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/import/abc-123-def-456');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`Progress: ${data.progress.percent}%`);
  console.log(`Message: ${data.progress.message}`);
  
  if (data.status === 'success') {
    console.log('Import complete!', data.result);
    ws.close();
  }
};
```

---

## Appendix B: Deployment Checklist

- [ ] PostgreSQL database created and migrated
- [ ] Redis running and accessible
- [ ] Environment variables configured
- [ ] models/ directory created with proper permissions
- [ ] Node.js and HyperFormula installed
- [ ] API service running (uvicorn)
- [ ] Celery worker running
- [ ] WebSocket connections tested
- [ ] API authentication configured
- [ ] CORS origins configured
- [ ] Monitoring and logging configured
- [ ] Backup strategy in place

---

**Document Version:** 1.0  
**Last Updated:** 2025-10-15  
**Author:** System Architect