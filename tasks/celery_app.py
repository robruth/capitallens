"""
Celery application configuration.

This module sets up Celery for background task processing with Redis
as the message broker and result backend.
"""

import os
from celery import Celery
from kombu import Exchange, Queue

# Get Redis URL from environment
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', REDIS_URL)

# Create Celery application
celery_app = Celery(
    'capitallens',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['tasks.import_tasks', 'tasks.validation_tasks']
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    
    # Timezone
    timezone='UTC',
    enable_utc=True,
    
    # Task execution
    task_track_started=True,
    task_time_limit=1800,  # 30 minutes hard timeout
    task_soft_time_limit=1500,  # 25 minutes soft timeout
    worker_prefetch_multiplier=1,  # One task at a time per worker
    
    # Results
    result_expires=3600,  # Results expire after 1 hour
    result_extended=True,  # Store more task metadata
    
    # Task routing
    task_default_queue='default',
    task_default_exchange='default',
    task_default_routing_key='default',
    
    # Worker configuration
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks (prevent memory leaks)
    worker_disable_rate_limits=False,
    
    # Task acknowledgement
    task_acks_late=True,  # Acknowledge task after completion
    task_reject_on_worker_lost=True,
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# Define task queues
celery_app.conf.task_queues = (
    Queue('default', Exchange('default'), routing_key='default'),
    Queue('import', Exchange('import'), routing_key='import.#'),
    Queue('validation', Exchange('validation'), routing_key='validation.#'),
)

# Task routes
celery_app.conf.task_routes = {
    'tasks.import_tasks.import_excel_file': {'queue': 'import', 'routing_key': 'import.excel'},
    'tasks.validation_tasks.validate_model': {'queue': 'validation', 'routing_key': 'validation.model'},
}

# Beat schedule (for periodic tasks if needed)
celery_app.conf.beat_schedule = {
    # Example: Clean up old temp files every hour
    # 'cleanup-temp-files': {
    #     'task': 'tasks.maintenance_tasks.cleanup_temp_files',
    #     'schedule': 3600.0,  # Every hour
    # },
}


if __name__ == '__main__':
    celery_app.start()