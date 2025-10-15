"""
Import router - Handle Excel file uploads and job tracking.

This module provides endpoints for uploading Excel files and checking
the status of import jobs.
"""

import os
import logging
import tempfile
import shutil
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

import redis
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from api.config import settings
from api.dependencies import get_db, get_current_user, verify_file_extension, verify_file_size
from api.schemas.import_schema import ImportStartResponse
from api.schemas.job_schema import JobStatusResponse, JobProgressResponse, JobListResponse, JobListItem
from backend.models.job import JobRun, JobType, JobStatus, JobProgress
from tasks.import_tasks import import_excel_file

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix='/import', tags=['import'])

# Redis client for progress tracking
redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


@router.post('/upload', response_model=ImportStartResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_excel_file(
    file: UploadFile = File(..., description="Excel file to import (.xlsx or .xlsm)"),
    model_name: str = Form(..., min_length=1, max_length=255, description="User-friendly model name"),
    validate: bool = Form(False, description="Whether to run post-import validation"),
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Upload Excel file and start import job.
    
    The file is uploaded to a temporary location and a background Celery task
    is started to process the import. Returns immediately with a job ID that
    can be used to track progress.
    
    **Workflow:**
    1. Upload file to temporary location
    2. Validate file type and size
    3. Create job record in database
    4. Enqueue Celery task
    5. Return job ID for status tracking
    
    **Progress Tracking:**
    - Poll GET /api/import/job/{job_id} for status
    - Connect to WebSocket /ws/import/{job_id} for real-time updates
    
    **Returns:**
    - 202 Accepted with job_id
    - URLs for status checking and WebSocket connection
    """
    logger.info(f"Upload request from {current_user}: {file.filename} as '{model_name}'")
    
    # Validate file extension
    verify_file_extension(file.filename)
    
    # Read file to temporary location
    temp_file = None
    try:
        # Create temporary file
        fd, temp_path = tempfile.mkstemp(
            suffix=Path(file.filename).suffix,
            dir=settings.TEMP_UPLOAD_DIR
        )
        
        # Write uploaded content
        with os.fdopen(fd, 'wb') as tmp:
            shutil.copyfileobj(file.file, tmp)
        
        temp_file = temp_path
        
        # Verify file size
        file_size = os.path.getsize(temp_path)
        verify_file_size(file_size)
        
        logger.info(f"File saved to {temp_path} ({file_size / 1024 / 1024:.2f} MB)")
        
        # Create job record (without job_id initially)
        job_run = JobRun(
            job_id='temp',  # Will be updated with Celery task ID
            job_type=JobType.IMPORT,
            status=JobStatus.PENDING,
            params={
                'filename': file.filename,
                'model_name': model_name,
                'validate': validate,
                'file_size_mb': round(file_size / 1024 / 1024, 2)
            },
            created_by=current_user
        )
        
        db.add(job_run)
        db.flush()
        
        # Start Celery task
        task = import_excel_file.apply_async(
            args=[temp_path, model_name, validate]
        )
        
        # Update job_id with Celery task ID
        job_run.job_id = task.id
        db.commit()
        
        logger.info(f"Started import task {task.id} for file: {file.filename}")
        
        return ImportStartResponse(
            job_id=task.id,
            message="Excel import job started",
            status_url=f"/api/import/job/{task.id}",
            websocket_url=f"/ws/import/{task.id}"
        )
        
    except HTTPException:
        # Clean up temp file on validation errors
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)
        raise
        
    except Exception as e:
        # Clean up temp file on any error
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)
        
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )


@router.get('/job/{job_id}', response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    Get current status of import job.
    
    Returns comprehensive job information including:
    - Job status (pending/processing/success/failed/cancelled)
    - Latest progress update
    - Results (if completed)
    - Error details (if failed)
    
    **Usage:**
    ```bash
    curl http://localhost:8000/api/import/job/abc-123-def-456
    ```
    
    **Status Values:**
    - `pending`: Job is queued, waiting for worker
    - `processing`: Job is currently running
    - `success`: Job completed successfully
    - `failed`: Job failed with error
    - `cancelled`: Job was cancelled
    """
    # Query job from database
    job_run = db.query(JobRun).filter_by(job_id=job_id).first()
    
    if not job_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    # Get latest progress from Redis (real-time)
    progress = None
    try:
        progress_data = redis_client.get(f'job_progress:{job_id}')
        if progress_data:
            progress_dict = json.loads(progress_data)
            progress = JobProgressResponse(**progress_dict)
    except Exception as e:
        logger.warning(f"Could not fetch progress from Redis for {job_id}: {e}")
    
    # If no Redis progress, try getting latest from database
    if not progress and job_run.progress:
        latest_progress = job_run.progress[-1]  # Get last progress entry
        progress = JobProgressResponse(
            stage=latest_progress.stage,
            percent=float(latest_progress.percent),
            message=latest_progress.message or "",
            timestamp=latest_progress.timestamp
        )
    
    return JobStatusResponse(
        job_id=job_run.job_id,
        job_type=job_run.job_type,
        status=job_run.status,
        created_at=job_run.created_at,
        started_at=job_run.started_at,
        completed_at=job_run.completed_at,
        progress=progress,
        result=job_run.result,
        error=job_run.error,
        model_id=job_run.model_id,
        created_by=job_run.created_by
    )


@router.get('/jobs', response_model=JobListResponse)
async def list_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    """
    List all jobs with pagination and filtering.
    
    **Filters:**
    - `job_type`: Filter by 'import' or 'validation'
    - `status`: Filter by job status
    
    **Example:**
    ```bash
    curl "http://localhost:8000/api/import/jobs?job_type=import&status=success&page=1"
    ```
    """
    # Build query
    query = db.query(JobRun)
    
    if job_type:
        query = query.filter_by(job_type=job_type)
    
    if status:
        query = query.filter_by(status=status)
    
    # Get total count
    total = query.count()
    
    # Get page of results
    jobs = query.order_by(JobRun.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size
    
    return JobListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=[JobListItem.model_validate(job) for job in jobs]
    )


@router.delete('/job/{job_id}', status_code=status.HTTP_204_NO_CONTENT)
async def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Cancel a pending or processing job.
    
    Only jobs that are pending or processing can be cancelled.
    Completed jobs (success/failed) cannot be cancelled.
    
    **Returns:**
    - 204 No Content if successfully cancelled
    - 404 if job not found
    - 400 if job cannot be cancelled (already completed)
    """
    job_run = db.query(JobRun).filter_by(job_id=job_id).first()
    
    if not job_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    # Check if job can be cancelled
    if job_run.status not in [JobStatus.PENDING, JobStatus.PROCESSING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job with status '{job_run.status}'"
        )
    
    # Update status to cancelled
    job_run.status = JobStatus.CANCELLED
    job_run.completed_at = datetime.utcnow()
    
    # Store cancellation info
    job_run.error = {
        'error': 'Job cancelled by user',
        'cancelled_by': current_user,
        'cancelled_at': datetime.utcnow().isoformat()
    }
    
    db.commit()
    
    # Try to revoke Celery task
    try:
        from tasks.celery_app import celery_app
        celery_app.control.revoke(job_id, terminate=True)
        logger.info(f"Revoked Celery task {job_id}")
    except Exception as e:
        logger.warning(f"Could not revoke Celery task {job_id}: {e}")
    
    logger.info(f"Job {job_id} cancelled by {current_user}")
    
    return None  # 204 No Content