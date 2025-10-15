"""
Job tracking models for background tasks.

This module defines SQLAlchemy models for tracking import and validation jobs,
including their progress and results.
"""

from enum import Enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, TIMESTAMP, ForeignKey, Numeric, Text,
    CheckConstraint, Index, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from backend.models.schema import Base


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = 'pending'
    PROCESSING = 'processing'
    SUCCESS = 'success'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class JobType(str, Enum):
    """Type of background job."""
    IMPORT = 'import'
    VALIDATION = 'validation'


class JobRun(Base):
    """
    Represents a background job execution (import or validation).
    
    Tracks the lifecycle of a job from creation through completion,
    storing parameters, results, and error information.
    """
    
    __tablename__ = 'job_runs'
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'success', 'failed', 'cancelled')",
            name='job_runs_status_check'
        ),
        CheckConstraint(
            "job_type IN ('import', 'validation')",
            name='job_runs_job_type_check'
        ),
        Index('idx_job_runs_status', 'status'),
        Index('idx_job_runs_created_at', 'created_at'),
        Index('idx_job_runs_model_id', 'model_id'),
        Index('idx_job_runs_type_status', 'job_type', 'status'),
        {'comment': 'Tracks background job executions (imports, validations)'}
    )
    
    job_id = Column(
        String(255),
        primary_key=True,
        nullable=False,
        comment='Celery task UUID'
    )
    job_type = Column(
        String(50),
        nullable=False,
        comment='Type of job: import or validation'
    )
    status = Column(
        String(20),
        nullable=False,
        server_default='pending',
        comment='Current job status'
    )
    created_at = Column(
        TIMESTAMP,
        server_default=text('CURRENT_TIMESTAMP'),
        nullable=False,
        comment='Job creation timestamp'
    )
    started_at = Column(
        TIMESTAMP,
        nullable=True,
        comment='Job start timestamp'
    )
    completed_at = Column(
        TIMESTAMP,
        nullable=True,
        comment='Job completion timestamp'
    )
    
    # Job parameters and results
    params = Column(
        JSONB,
        server_default='{}',
        nullable=False,
        comment='Input parameters for the job'
    )
    result = Column(
        JSONB,
        nullable=True,
        comment='Job execution results'
    )
    error = Column(
        JSONB,
        nullable=True,
        comment='Error details if job failed'
    )
    
    # Associated model (if applicable)
    model_id = Column(
        Integer,
        ForeignKey('models.id', ondelete='SET NULL'),
        nullable=True,
        comment='Associated model ID (for imports/validations)'
    )
    
    # Metadata
    created_by = Column(
        String(255),
        nullable=True,
        comment='User or API key that created the job'
    )
    
    # Relationships
    model = relationship('Model', back_populates='jobs')
    progress = relationship(
        'JobProgress',
        back_populates='job',
        cascade='all, delete-orphan',
        order_by='JobProgress.timestamp'
    )
    
    def __repr__(self):
        return f"<JobRun(job_id='{self.job_id}', type='{self.job_type}', status='{self.status}')>"
    
    def to_dict(self) -> dict:
        """Convert job to dictionary representation."""
        return {
            'job_id': self.job_id,
            'job_type': self.job_type,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'params': self.params,
            'result': self.result,
            'error': self.error,
            'model_id': self.model_id,
            'created_by': self.created_by
        }
    
    def duration_seconds(self) -> float:
        """Calculate job duration in seconds."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return delta.total_seconds()
        return 0.0
    
    def is_complete(self) -> bool:
        """Check if job has completed (success, failed, or cancelled)."""
        return self.status in [JobStatus.SUCCESS, JobStatus.FAILED, JobStatus.CANCELLED]
    
    def is_running(self) -> bool:
        """Check if job is currently running."""
        return self.status == JobStatus.PROCESSING


class JobProgress(Base):
    """
    Represents a progress update for a job.
    
    Stores detailed progress information as the job executes,
    including stage, percentage, and descriptive messages.
    """
    
    __tablename__ = 'job_progress'
    __table_args__ = (
        Index('idx_job_progress_job_id', 'job_id'),
        Index('idx_job_progress_timestamp', 'timestamp'),
        Index('idx_job_progress_job_stage', 'job_id', 'stage'),
        {'comment': 'Detailed progress tracking for jobs'}
    )
    
    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False
    )
    job_id = Column(
        String(255),
        ForeignKey('job_runs.job_id', ondelete='CASCADE'),
        nullable=False,
        comment='Associated job ID'
    )
    stage = Column(
        String(50),
        nullable=False,
        comment='Current stage (e.g., parsing, evaluation, insertion)'
    )
    percent = Column(
        Numeric(5, 2),
        nullable=False,
        comment='Progress percentage (0.00 to 100.00)'
    )
    message = Column(
        Text,
        nullable=True,
        comment='Human-readable progress message'
    )
    timestamp = Column(
        TIMESTAMP,
        server_default=text('CURRENT_TIMESTAMP'),
        nullable=False,
        comment='Progress update timestamp'
    )
    
    # Relationship
    job = relationship('JobRun', back_populates='progress')
    
    def __repr__(self):
        return f"<JobProgress(job_id='{self.job_id}', stage='{self.stage}', percent={self.percent})>"
    
    def to_dict(self) -> dict:
        """Convert progress to dictionary representation."""
        return {
            'id': self.id,
            'job_id': self.job_id,
            'stage': self.stage,
            'percent': float(self.percent),
            'message': self.message,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


# Update Model class to include jobs relationship
# This should be added to backend/models/schema.py:
# from backend.models.job import JobRun
# 
# class Model(Base):
#     # ... existing fields ...
#     jobs = relationship('JobRun', back_populates='model')