"""
FastAPI application for Excel import system.

This module creates and configures the FastAPI application, registering
all routers and middleware.
"""

import logging
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from api.config import settings
from api.routers import import_router, models, validation, websocket
from api.schemas.common import ErrorResponse, HealthCheckResponse
from backend.models.schema import Base
from datetime import datetime
import os

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format=settings.LOG_FORMAT,
    handlers=[
        logging.FileHandler(settings.LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Create database engine for health checks
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown events.
    """
    # Startup
    logger.info(f"Starting {settings.API_TITLE} v{settings.API_VERSION}")
    logger.info(f"Database: {settings.DATABASE_URL.split('@')[-1]}")  # Hide credentials
    logger.info(f"Redis: {settings.REDIS_URL}")
    
    # Ensure database tables exist
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    
    # Ensure temp upload directory exists
    import os
    os.makedirs(settings.TEMP_UPLOAD_DIR, exist_ok=True)
    logger.info(f"Temp upload directory: {settings.TEMP_UPLOAD_DIR}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")


# Create FastAPI application
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS
)


# Exception handlers

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            detail={"message": str(exc)} if settings.DEBUG else None,
            path=str(request.url)
        ).model_dump()
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Handle 404 Not Found errors."""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(
            error="Resource not found",
            detail={"path": str(request.url)},
            path=str(request.url)
        ).model_dump()
    )


# Register routers with API prefix
app.include_router(import_router.router, prefix=settings.API_PREFIX)
app.include_router(models.router, prefix=settings.API_PREFIX)
app.include_router(validation.router, prefix=settings.API_PREFIX)
app.include_router(websocket.router)  # WebSocket doesn't use /api prefix


# Root endpoints

@app.get('/', include_in_schema=False)
async def root():
    """
    Root endpoint - redirect to docs.
    """
    return {
        'message': f'Welcome to {settings.API_TITLE}',
        'version': settings.API_VERSION,
        'docs': '/docs',
        'redoc': '/redoc',
        'openapi': '/openapi.json'
    }


@app.get('/health', response_model=HealthCheckResponse, tags=['health'])
async def health_check():
    """
    Health check endpoint.
    
    Checks connectivity to:
    - Database (PostgreSQL)
    - Redis
    - Celery workers
    
    **Returns:**
    - Overall health status
    - Component-level status
    - Timestamp and version
    
    **Example:**
    ```bash
    curl http://localhost:8000/health
    ```
    """
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.utcnow(),
        'version': settings.API_VERSION,
        'database': 'unknown',
        'redis': 'unknown',
        'celery': 'unknown'
    }
    
    # Check database
    try:
        with SessionLocal() as session:
            session.execute(text('SELECT 1'))
        health_status['database'] = 'connected'
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status['database'] = 'disconnected'
        health_status['status'] = 'unhealthy'
    
    # Check Redis
    try:
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        redis_client.ping()
        health_status['redis'] = 'connected'
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        health_status['redis'] = 'disconnected'
        health_status['status'] = 'degraded'
    
    # Check Celery workers
    try:
        from tasks.celery_app import celery_app
        
        # Get active workers
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        
        if active_workers and len(active_workers) > 0:
            health_status['celery'] = f'active ({len(active_workers)} workers)'
        else:
            health_status['celery'] = 'no workers'
            health_status['status'] = 'degraded'
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        health_status['celery'] = 'unknown'
    
    return HealthCheckResponse(**health_status)


@app.get('/api/ping', tags=['health'])
async def ping():
    """
    Simple ping endpoint for load balancers.
    
    **Returns:**
    ```json
    {"ping": "pong"}
    ```
    """
    return {'ping': 'pong'}


# Middleware for request logging

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests."""
    logger.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"{request.method} {request.url.path} - {response.status_code}")
    return response


if __name__ == '__main__':
    import uvicorn
    
    uvicorn.run(
        'api.main:app',
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        log_level=settings.LOG_LEVEL.lower()
    )