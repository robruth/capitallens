"""add job tracking tables

Revision ID: 002_job_tracking
Revises: 001_initial_schema
Create Date: 2025-10-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_job_tracking'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create job tracking tables for background task management.
    
    Tables created:
    - job_runs: Track background jobs (imports, validations)
    - job_progress: Detailed progress tracking for jobs
    """
    
    # Create job_runs table
    op.create_table(
        'job_runs',
        sa.Column('job_id', sa.String(length=255), nullable=False, comment='Celery task UUID'),
        sa.Column('job_type', sa.String(length=50), nullable=False, comment='Type of job: import or validation'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending', comment='Current job status'),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='Job creation timestamp'),
        sa.Column('started_at', sa.TIMESTAMP(), nullable=True, comment='Job start timestamp'),
        sa.Column('completed_at', sa.TIMESTAMP(), nullable=True, comment='Job completion timestamp'),
        sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False, comment='Input parameters for the job'),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Job execution results'),
        sa.Column('error', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Error details if job failed'),
        sa.Column('model_id', sa.Integer(), nullable=True, comment='Associated model ID (for imports/validations)'),
        sa.Column('created_by', sa.String(length=255), nullable=True, comment='User or API key that created the job'),
        sa.CheckConstraint("status IN ('pending', 'processing', 'success', 'failed', 'cancelled')", name='job_runs_status_check'),
        sa.CheckConstraint("job_type IN ('import', 'validation')", name='job_runs_job_type_check'),
        sa.ForeignKeyConstraint(['model_id'], ['models.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('job_id'),
        comment='Tracks background job executions (imports, validations)'
    )
    
    # Create indexes for job_runs
    op.create_index('idx_job_runs_status', 'job_runs', ['status'])
    op.create_index('idx_job_runs_created_at', 'job_runs', ['created_at'])
    op.create_index('idx_job_runs_model_id', 'job_runs', ['model_id'])
    op.create_index('idx_job_runs_type_status', 'job_runs', ['job_type', 'status'])
    
    # Create job_progress table
    op.create_table(
        'job_progress',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=255), nullable=False, comment='Associated job ID'),
        sa.Column('stage', sa.String(length=50), nullable=False, comment='Current stage (e.g., parsing, evaluation, insertion)'),
        sa.Column('percent', sa.Numeric(precision=5, scale=2), nullable=False, comment='Progress percentage (0.00 to 100.00)'),
        sa.Column('message', sa.Text(), nullable=True, comment='Human-readable progress message'),
        sa.Column('timestamp', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='Progress update timestamp'),
        sa.ForeignKeyConstraint(['job_id'], ['job_runs.job_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        comment='Detailed progress tracking for jobs'
    )
    
    # Create indexes for job_progress
    op.create_index('idx_job_progress_job_id', 'job_progress', ['job_id'])
    op.create_index('idx_job_progress_timestamp', 'job_progress', ['timestamp'])
    op.create_index('idx_job_progress_job_stage', 'job_progress', ['job_id', 'stage'])


def downgrade() -> None:
    """
    Remove job tracking tables.
    """
    # Drop indexes first
    op.drop_index('idx_job_progress_job_stage', table_name='job_progress')
    op.drop_index('idx_job_progress_timestamp', table_name='job_progress')
    op.drop_index('idx_job_progress_job_id', table_name='job_progress')
    
    # Drop job_progress table
    op.drop_table('job_progress')
    
    # Drop job_runs indexes
    op.drop_index('idx_job_runs_type_status', table_name='job_runs')
    op.drop_index('idx_job_runs_model_id', table_name='job_runs')
    op.drop_index('idx_job_runs_created_at', table_name='job_runs')
    op.drop_index('idx_job_runs_status', table_name='job_runs')
    
    # Drop job_runs table
    op.drop_table('job_runs')