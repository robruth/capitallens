"""
Validation background tasks.

This module defines Celery tasks for model validation with progress tracking.
"""

import logging
import traceback
from datetime import datetime
from typing import Dict, Any

from celery import Task
from sqlalchemy.orm import Session

from tasks.celery_app import celery_app
from tasks.import_tasks import ImportTask, get_db_session
from services.validation_service import ValidationService
from backend.models.job import JobRun, JobStatus

logger = logging.getLogger(__name__)


@celery_app.task(base=ImportTask, bind=True, name='tasks.validation_tasks.validate_model')
def validate_model(self, model_id: int) -> Dict[str, Any]:
    """
    Background task to validate an imported model.
    
    Args:
        model_id: Model ID to validate
    
    Returns:
        Validation results dictionary:
        {
            'status': 'passed' | 'failed' | 'partial',
            'total': int,
            'matches': int,
            'mismatches': int,
            'errors': int,
            'null_calculated': int,
            'tolerance': float,
            'mismatch_cells': [...]
        }
    """
    job_id = self.request.id
    logger.info(f"Starting validation task {job_id} for model: {model_id}")
    
    try:
        # Update job status to PROCESSING
        self.update_job_status(
            job_id=job_id,
            status=JobStatus.PROCESSING,
            started_at=datetime.utcnow()
        )
        
        # Execute validation with progress callback
        with get_db_session() as session:
            service = ValidationService(
                db_session=session,
                progress_callback=self.on_progress
            )
            
            result = service.validate_model(model_id=model_id)
        
        # Check if validation encountered an error
        if 'error' in result:
            raise Exception(result['error'])
        
        # Update job status to SUCCESS
        self.update_job_status(
            job_id=job_id,
            status=JobStatus.SUCCESS,
            completed_at=datetime.utcnow(),
            result=result,
            model_id=model_id
        )
        
        logger.info(f"Validation task {job_id} completed: {result['status']}")
        return result
        
    except Exception as e:
        # Capture full error details
        error_details = {
            'error': str(e),
            'traceback': traceback.format_exc(),
            'model_id': model_id
        }
        
        logger.error(f"Validation task {job_id} failed: {e}", exc_info=True)
        
        # Update job status to FAILED
        self.update_job_status(
            job_id=job_id,
            status=JobStatus.FAILED,
            completed_at=datetime.utcnow(),
            error=error_details,
            model_id=model_id
        )
        
        # Update progress to show failure
        self.on_progress('failed', 0, f"Validation failed: {str(e)}")
        
        # Re-raise for Celery to handle
        raise


@celery_app.task(name='tasks.validation_tasks.get_validation_summary')
def get_validation_summary(model_id: int) -> Dict[str, Any]:
    """
    Get quick validation summary without full re-validation.
    
    Args:
        model_id: Model ID
    
    Returns:
        Validation summary dictionary
    """
    try:
        with get_db_session() as session:
            service = ValidationService(db_session=session)
            summary = service.get_validation_summary(model_id)
            
            return summary
            
    except Exception as e:
        logger.error(f"Error getting validation summary for model {model_id}: {e}")
        return {
            'error': str(e),
            'model_id': model_id
        }


@celery_app.task(name='tasks.validation_tasks.get_mismatches')
def get_mismatches(model_id: int, limit: int = 100) -> Dict[str, Any]:
    """
    Get cells with mismatches for a model.
    
    Args:
        model_id: Model ID
        limit: Maximum number of results
    
    Returns:
        Dictionary with mismatch list
    """
    try:
        with get_db_session() as session:
            service = ValidationService(db_session=session)
            mismatches = service.get_mismatches(model_id, limit)
            
            return {
                'model_id': model_id,
                'count': len(mismatches),
                'limit': limit,
                'mismatches': mismatches
            }
            
    except Exception as e:
        logger.error(f"Error getting mismatches for model {model_id}: {e}")
        return {
            'error': str(e),
            'model_id': model_id
        }


@celery_app.task(name='tasks.validation_tasks.get_null_calculated_cells')
def get_null_calculated_cells(model_id: int, limit: int = 100) -> Dict[str, Any]:
    """
    Get cells where calculated_value is NULL but formula exists.
    
    Args:
        model_id: Model ID
        limit: Maximum number of results
    
    Returns:
        Dictionary with NULL calculated cells list
    """
    try:
        with get_db_session() as session:
            service = ValidationService(db_session=session)
            null_cells = service.get_null_calculated_cells(model_id, limit)
            
            return {
                'model_id': model_id,
                'count': len(null_cells),
                'limit': limit,
                'null_cells': null_cells
            }
            
    except Exception as e:
        logger.error(f"Error getting NULL calculated cells for model {model_id}: {e}")
        return {
            'error': str(e),
            'model_id': model_id
        }