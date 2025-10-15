"""
WebSocket router - Real-time progress updates.

This module provides WebSocket endpoints for streaming job progress updates.
"""

import json
import logging
import asyncio
from typing import Optional

import redis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, status
from sqlalchemy.orm import Session

from api.config import settings
from api.dependencies import get_db
from backend.models.job import JobRun, JobStatus

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=['websocket'])

# Redis client
redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


@router.websocket('/ws/import/{job_id}')
async def websocket_import_progress(
    websocket: WebSocket,
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time import progress updates.
    
    Streams progress updates as the job executes, sending JSON messages with:
    - Current progress (stage, percent, message)
    - Job status changes
    - Final results or errors
    
    **Connection:**
    ```javascript
    const ws = new WebSocket('ws://localhost:8000/ws/import/abc-123-def-456');
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log(`Progress: ${data.progress.percent}%`);
        
        if (data.status === 'success') {
            console.log('Import complete!', data.result);
            ws.close();
        }
    };
    ```
    
    **Message Format:**
    ```json
    {
        "job_id": "abc-123-def-456",
        "status": "processing",
        "progress": {
            "stage": "evaluation",
            "percent": 65.5,
            "message": "Evaluating formulas...",
            "timestamp": "2025-10-15T12:30:45Z"
        }
    }
    ```
    
    **Final Message (Success):**
    ```json
    {
        "job_id": "abc-123-def-456",
        "status": "success",
        "completed_at": "2025-10-15T12:31:00Z",
        "result": {
            "model_id": 123,
            "stats": {...}
        }
    }
    ```
    
    **Final Message (Failed):**
    ```json
    {
        "job_id": "abc-123-def-456",
        "status": "failed",
        "completed_at": "2025-10-15T12:30:50Z",
        "error": {
            "error": "Formula evaluation failed",
            "traceback": "..."
        }
    }
    ```
    """
    await websocket.accept()
    logger.info(f"WebSocket connection established for job {job_id}")
    
    try:
        # Verify job exists
        job_run = db.query(JobRun).filter_by(job_id=job_id).first()
        if not job_run:
            await websocket.send_json({
                'error': f'Job {job_id} not found',
                'job_id': job_id
            })
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Send initial status
        await websocket.send_json({
            'job_id': job_id,
            'status': job_run.status,
            'message': 'Connected to job progress stream'
        })
        
        last_progress = None
        last_status = job_run.status
        
        # Stream progress until job completes
        while True:
            # Refresh job status from database
            db.refresh(job_run)
            
            # Check if status changed
            if job_run.status != last_status:
                await websocket.send_json({
                    'job_id': job_id,
                    'status': job_run.status,
                    'message': f'Job status changed to {job_run.status}'
                })
                last_status = job_run.status
            
            # Get current progress from Redis
            try:
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
            except Exception as e:
                logger.warning(f"Error reading progress from Redis for {job_id}: {e}")
            
            # Check if job is complete
            if job_run.status in [JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED]:
                # Send final status message
                final_message = {
                    'job_id': job_id,
                    'status': job_run.status,
                    'completed_at': job_run.completed_at.isoformat() if job_run.completed_at else None
                }
                
                if job_run.status == JobStatus.SUCCESS:
                    final_message['result'] = job_run.result
                elif job_run.status == JobStatus.FAILED:
                    final_message['error'] = job_run.error
                
                await websocket.send_json(final_message)
                
                logger.info(f"Job {job_id} completed with status {job_run.status}")
                break
            
            # Wait before checking again (500ms for responsive updates)
            await asyncio.sleep(0.5)
        
        # Close connection gracefully
        await websocket.close()
        logger.info(f"WebSocket connection closed for job {job_id}")
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected from job {job_id}")
    
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {e}", exc_info=True)
        try:
            await websocket.send_json({
                'error': str(e),
                'job_id': job_id
            })
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except:
            pass


@router.websocket('/ws/validation/{job_id}')
async def websocket_validation_progress(
    websocket: WebSocket,
    job_id: str,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time validation progress updates.
    
    Same functionality as /ws/import/{job_id} but specifically for
    validation jobs. Uses the same progress tracking mechanism.
    
    **Example:**
    ```javascript
    const ws = new WebSocket('ws://localhost:8000/ws/validation/abc-123');
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log(`Validation: ${data.progress.percent}%`);
    };
    ```
    """
    # Reuse the same logic as import progress
    await websocket_import_progress(websocket, job_id, db)