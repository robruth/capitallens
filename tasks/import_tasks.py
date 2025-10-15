"""
Import background tasks.

This module defines Celery tasks for Excel file imports with progress tracking.
"""

import os
import json
import logging
import traceback
from datetime import datetime
from typing import Dict, Any
import redis

from celery import Task
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from tasks.celery_app import celery_app
from services.excel_import_service import ExcelImportService
from backend.models.job import JobRun, JobProgress, JobStatus
from backend.models.schema import Base

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost/dcmodel')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Create Redis client
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

# Create database engine and session factory
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_session() -> Session:
    """Get database session."""
    return SessionLocal()


class ImportTask(Task):
    """
    Base task class with progress tracking.
    
    Provides methods for updating job progress in both Redis (for real-time)
    and PostgreSQL (for persistence).
    """
    
    def on_progress(self, stage: str, percent: float, message: str):
        """
        Update job progress in Redis and database.
        
        Args:
            stage: Current stage (e.g., 'parsing', 'evaluation')
            percent: Progress percentage (0-100)
            message: Human-readable progress message
        """
        job_id = self.request.id
        
        try:
            # Store in Redis for real-time WebSocket updates (expires in 1 hour)
            progress_data = {
                'stage': stage,
                'percent': float(percent),
                'message': message,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            redis_client.setex(
                f'job_progress:{job_id}',
                3600,  # 1 hour expiry
                json.dumps(progress_data)
            )
            
            # Store in database for persistence
            with get_db_session() as session:
                progress = JobProgress(
                    job_id=job_id,
                    stage=stage,
                    percent=percent,
                    message=message
                )
                session.add(progress)
                session.commit()
                
            logger.debug(f"Progress updated: {job_id} - {stage} ({percent}%)")
            
        except Exception as e:
            logger.error(f"Error updating progress for {job_id}: {e}")
    
    def update_job_status(self, job_id: str, status: str, **kwargs):
        """
        Update job status in database.
        
        Args:
            job_id: Job ID
            status: New status
            **kwargs: Additional fields to update (result, error, etc.)
        """
        try:
            with get_db_session() as session:
                job_run = session.query(JobRun).filter_by(job_id=job_id).first()
                if job_run:
                    job_run.status = status
                    
                    # Update additional fields
                    for key, value in kwargs.items():
                        if hasattr(job_run, key):
                            setattr(job_run, key, value)
                    
                    session.commit()
                    logger.info(f"Job {job_id} status updated to {status}")
                else:
                    logger.warning(f"Job {job_id} not found in database")
        except Exception as e:
            logger.error(f"Error updating job status for {job_id}: {e}")


@celery_app.task(base=ImportTask, bind=True, name='tasks.import_tasks.import_excel_file')
def import_excel_file(self, file_path: str, model_name: str, 
                     validate: bool = False) -> Dict[str, Any]:
    """
    Background task to import Excel file.
    
    Args:
        file_path: Path to uploaded Excel file
        model_name: User-provided model name
        validate: Whether to run post-import validation
    
    Returns:
        Import results dictionary:
        {
            'model_id': int,
            'stats': dict,
            'validation_results': dict or None,
            'errors': list
        }
    """
    job_id = self.request.id
    logger.info(f"Starting import task {job_id} for file: {file_path}")
    
    try:
        # Update job status to PROCESSING
        self.update_job_status(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            started_at=datetime.utcnow()
        )
        
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
        
        # Check if import was successful
        if result.get('model_id') is None:
            # Import failed
            raise Exception(f"Import failed: {result.get('errors', ['Unknown error'])}")
        
        # Update job status to SUCCESS
        self.update_job_status(
            job_id=job_id,
            status=JobStatus.SUCCESS,
            completed_at=datetime.utcnow(),
            result=result,
            model_id=result.get('model_id')
        )
        
        # Clean up temporary file if it's in temp directory
        if file_path.startswith('/tmp/') or file_path.startswith(os.path.join(os.getcwd(), 'tmp')):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up temporary file: {file_path}")
            except Exception as e:
                logger.warning(f"Could not remove temp file {file_path}: {e}")
        
        logger.info(f"Import task {job_id} completed successfully. Model ID: {result.get('model_id')}")
        return result
        
    except Exception as e:
        # Capture full error details
        error_details = {
            'error': str(e),
            'traceback': traceback.format_exc(),
            'file_path': file_path,
            'model_name': model_name
        }
        
        logger.error(f"Import task {job_id} failed: {e}", exc_info=True)
        
        # Update job status to FAILED
        self.update_job_status(
            job_id=job_id,
            status=JobStatus.FAILED,
            completed_at=datetime.utcnow(),
            error=error_details
        )
        
        # Update progress to show failure
        self.on_progress('failed', 0, f"Import failed: {str(e)}")
        
        # Re-raise for Celery to handle
        raise


@celery_app.task(name='tasks.import_tasks.cleanup_old_jobs')
def cleanup_old_jobs(days_to_keep: int = 30) -> Dict[str, int]:
    """
    Clean up old job records and progress entries.
    
    Args:
        days_to_keep: Number of days to keep job records
    
    Returns:
        Dictionary with cleanup statistics
    """
    logger.info(f"Starting cleanup of jobs older than {days_to_keep} days")
    
    try:
        with get_db_session() as session:
            cutoff_date = datetime.utcnow() - datetime.timedelta(days=days_to_keep)
            
            # Delete old job progress entries
            deleted_progress = session.query(JobProgress).filter(
                JobProgress.timestamp < cutoff_date
            ).delete()
            
            # Delete old completed jobs
            deleted_jobs = session.query(JobRun).filter(
                JobRun.completed_at < cutoff_date,
                JobRun.status.in_([JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED])
            ).delete()
            
            session.commit()
            
            logger.info(f"Cleanup complete: {deleted_jobs} jobs, {deleted_progress} progress entries deleted")
            
            return {
                'deleted_jobs': deleted_jobs,
                'deleted_progress': deleted_progress,
                'cutoff_date': cutoff_date.isoformat()
            }
            
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        return {
            'error': str(e),
            'deleted_jobs': 0,
            'deleted_progress': 0
        }


@celery_app.task(name='tasks.import_tasks.get_job_status')
def get_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get current status of a job.
    
    Args:
        job_id: Job ID to check
    
    Returns:
        Job status dictionary
    """
    try:
        with get_db_session() as session:
            job_run = session.query(JobRun).filter_by(job_id=job_id).first()
            
            if not job_run:
                return {'error': 'Job not found', 'job_id': job_id}
            
            # Get latest progress from Redis
            progress_data = redis_client.get(f'job_progress:{job_id}')
            progress = json.loads(progress_data) if progress_data else None
            
            return {
                'job_id': job_run.job_id,
                'job_type': job_run.job_type,
                'status': job_run.status,
                'created_at': job_run.created_at.isoformat() if job_run.created_at else None,
                'started_at': job_run.started_at.isoformat() if job_run.started_at else None,
                'completed_at': job_run.completed_at.isoformat() if job_run.completed_at else None,
                'progress': progress,
                'result': job_run.result,
                'error': job_run.error,
                'model_id': job_run.model_id
            }
            
    except Exception as e:
        logger.error(f"Error getting job status for {job_id}: {e}")
        return {
            'error': str(e),
            'job_id': job_id
        }