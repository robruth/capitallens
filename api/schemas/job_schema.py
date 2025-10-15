"""
Job-related Pydantic schemas.

This module contains schemas for job status, progress, and results.
"""

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class JobStatusEnum(str, Enum):
    """Job execution status."""
    PENDING = 'pending'
    PROCESSING = 'processing'
    SUCCESS = 'success'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class JobTypeEnum(str, Enum):
    """Type of background job."""
    IMPORT = 'import'
    VALIDATION = 'validation'


class JobProgressResponse(BaseModel):
    """Real-time progress update."""
    
    stage: str = Field(..., description="Current stage (e.g., 'parsing', 'evaluation')")
    percent: float = Field(..., ge=0, le=100, description="Progress percentage")
    message: str = Field(..., description="Human-readable progress message")
    timestamp: datetime = Field(..., description="Progress update timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "stage": "evaluation",
                "percent": 65.5,
                "message": "Evaluating formula 325/500",
                "timestamp": "2025-10-15T12:30:45Z"
            }
        }


class JobProgressDetail(BaseModel):
    """Detailed progress record from database."""
    
    id: int
    job_id: str
    stage: str
    percent: float
    message: Optional[str]
    timestamp: datetime
    
    class Config:
        from_attributes = True


class JobStatusResponse(BaseModel):
    """Comprehensive job status response."""
    
    job_id: str = Field(..., description="Unique job identifier (Celery task ID)")
    job_type: JobTypeEnum = Field(..., description="Type of job")
    status: JobStatusEnum = Field(..., description="Current job status")
    created_at: datetime = Field(..., description="Job creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Job start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Job completion timestamp")
    
    # Progress information
    progress: Optional[JobProgressResponse] = Field(None, description="Latest progress update")
    
    # Results
    result: Optional[Dict[str, Any]] = Field(None, description="Job results (if completed)")
    error: Optional[Dict[str, Any]] = Field(None, description="Error details (if failed)")
    
    # Associated model
    model_id: Optional[int] = Field(None, description="Associated model ID")
    
    # Metadata
    created_by: Optional[str] = Field(None, description="User who created the job")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "job_id": "abc-123-def-456",
                "job_type": "import",
                "status": "processing",
                "created_at": "2025-10-15T12:00:00Z",
                "started_at": "2025-10-15T12:00:05Z",
                "completed_at": None,
                "progress": {
                    "stage": "evaluation",
                    "percent": 65.5,
                    "message": "Evaluating formulas...",
                    "timestamp": "2025-10-15T12:00:30Z"
                },
                "result": None,
                "error": None,
                "model_id": None,
                "created_by": "api_key_123"
            }
        }


class JobCreateResponse(BaseModel):
    """Response when a job is created."""
    
    job_id: str = Field(..., description="Unique job identifier")
    message: str = Field(default="Job created successfully", description="Success message")
    status_url: str = Field(..., description="URL to check job status")
    websocket_url: str = Field(..., description="WebSocket URL for real-time updates")
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "abc-123-def-456",
                "message": "Import job started",
                "status_url": "/api/import/job/abc-123-def-456",
                "websocket_url": "/ws/import/abc-123-def-456"
            }
        }


class JobListItem(BaseModel):
    """Job list item for job history."""
    
    job_id: str
    job_type: JobTypeEnum
    status: JobStatusEnum
    created_at: datetime
    completed_at: Optional[datetime]
    model_id: Optional[int]
    
    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    """Paginated list of jobs."""
    
    total: int = Field(..., description="Total number of jobs")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    items: list[JobListItem] = Field(..., description="Jobs in current page")


class JobStatsResponse(BaseModel):
    """Job statistics."""
    
    total_jobs: int = Field(..., description="Total jobs")
    pending: int = Field(..., description="Pending jobs")
    processing: int = Field(..., description="Processing jobs")
    success: int = Field(..., description="Successful jobs")
    failed: int = Field(..., description="Failed jobs")
    cancelled: int = Field(..., description="Cancelled jobs")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_jobs": 150,
                "pending": 2,
                "processing": 1,
                "success": 140,
                "failed": 5,
                "cancelled": 2
            }
        }