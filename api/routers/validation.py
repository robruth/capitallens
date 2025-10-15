"""
Validation router - Trigger and manage model validation.

This module provides endpoints for validating imported models.
"""

import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.config import settings
from api.dependencies import get_db, get_current_user
from api.schemas.job_schema import JobCreateResponse
from backend.models.schema import Model
from backend.models.job import JobRun, JobType, JobStatus
from tasks.validation_tasks import validate_model

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix='/models/{model_id}', tags=['validation'])


@router.post('/validate', response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_validation(
    model_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Trigger post-import validation for a model.
    
    Starts a background job to validate all formula cells by comparing
    calculated values against Excel's computed values.
    
    **Validation Process:**
    1. Load all formula cells
    2. Compare calculated_value vs raw_value (or calculated_text vs raw_text)
    3. Apply tolerance (1e-6 for numeric)
    4. Report matches, mismatches, and errors
    
    **Returns:**
    - 202 Accepted with job_id
    - URLs for status checking and WebSocket
    
    **Example:**
    ```bash
    curl -X POST http://localhost:8000/api/models/123/validate
    ```
    """
    # Check model exists
    model = db.query(Model).filter_by(id=model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found"
        )
    
    # Create job record (temporary ID will be replaced)
    job_run = JobRun(
        job_id='temp',
        job_type=JobType.VALIDATION,
        status=JobStatus.PENDING,
        model_id=model_id,
        params={'model_id': model_id},
        created_by=current_user
    )
    
    db.add(job_run)
    db.flush()
    
    # Start Celery task
    task = validate_model.apply_async(args=[model_id])
    
    # Update job_id with Celery task ID
    job_run.job_id = task.id
    db.commit()
    
    logger.info(f"Started validation task {task.id} for model {model_id}")
    
    return JobCreateResponse(
        job_id=task.id,
        message="Validation job started",
        status_url=f"/api/import/job/{task.id}",
        websocket_url=f"/ws/import/{task.id}"
    )


@router.get('/validation/summary')
async def get_validation_summary(
    model_id: int,
    db: Session = Depends(get_db)
):
    """
    Get quick validation summary without re-running validation.
    
    Returns counts of matches, mismatches, and NULL values based on
    existing data in the database.
    
    **Fast Operation:** Does not re-evaluate formulas, just queries database.
    
    **Example:**
    ```bash
    curl http://localhost:8000/api/models/123/validation/summary
    ```
    """
    # Check model exists
    model = db.query(Model).filter_by(id=model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found"
        )
    
    from services.validation_service import ValidationService
    
    service = ValidationService(db_session=db)
    summary = service.get_validation_summary(model_id)
    
    return summary


@router.get('/validation/mismatches')
async def get_mismatches(
    model_id: int,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Get cells with calculation mismatches.
    
    Returns cells where our calculated value differs from Excel's
    computed value by more than the tolerance threshold.
    
    **Query Parameters:**
    - `limit`: Maximum number of results (default: 100)
    
    **Example:**
    ```bash
    curl "http://localhost:8000/api/models/123/validation/mismatches?limit=50"
    ```
    """
    # Check model exists
    model = db.query(Model).filter_by(id=model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found"
        )
    
    from services.validation_service import ValidationService
    
    service = ValidationService(db_session=db)
    mismatches = service.get_mismatches(model_id, limit)
    
    return {
        'model_id': model_id,
        'count': len(mismatches),
        'limit': limit,
        'mismatches': mismatches
    }


@router.get('/validation/null-calculated')
async def get_null_calculated(
    model_id: int,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Get cells where calculated_value is NULL but formula exists.
    
    These cells indicate formulas that failed to evaluate or were
    not supported by the evaluation engines.
    
    **Query Parameters:**
    - `limit`: Maximum number of results (default: 100)
    
    **Example:**
    ```bash
    curl "http://localhost:8000/api/models/123/validation/null-calculated?limit=50"
    ```
    """
    # Check model exists
    model = db.query(Model).filter_by(id=model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found"
        )
    
    from services.validation_service import ValidationService
    
    service = ValidationService(db_session=db)
    null_cells = service.get_null_calculated_cells(model_id, limit)
    
    return {
        'model_id': model_id,
        'count': len(null_cells),
        'limit': limit,
        'null_cells': null_cells
    }