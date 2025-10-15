"""
Application configuration using Pydantic Settings.

This module manages all configuration from environment variables.
"""

import os
from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Configuration
    API_TITLE: str = "Capital Lens Excel Import API"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = "REST API for Excel file imports with background job processing"
    API_PREFIX: str = "/api"
    
    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    RELOAD: bool = False
    
    # Database Configuration
    DATABASE_URL: str = "postgresql://postgres:password@localhost/dcmodel"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_PRE_PING: bool = True
    
    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Celery Configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # File Storage Configuration
    MODELS_DIR: str = "models/"
    TEMP_UPLOAD_DIR: str = "/tmp/excel_uploads"
    MAX_FILE_SIZE_MB: int = 100
    ALLOWED_EXTENSIONS: List[str] = [".xlsx", ".xlsm"]
    
    # Formula Evaluation Settings
    TOLERANCE: float = 1e-6
    MAX_CIRCULAR_ITERATIONS: int = 100
    CONVERGENCE_THRESHOLD: float = 1e-6
    HYPERFORMULA_WRAPPER: str = "scripts/hyperformula_wrapper.js"
    HYPERFORMULA_NODE_PATH: Optional[str] = None  # Optional: path to Node.js binary
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "api.log"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # Security Configuration
    API_KEY_HEADER: str = "X-API-Key"
    ENABLE_API_KEY_AUTH: bool = False  # Set to True in production
    
    # Job Configuration
    JOB_RETENTION_DAYS: int = 30  # Keep job records for 30 days
    PROGRESS_CACHE_EXPIRY: int = 3600  # Redis progress cache expiry (1 hour)
    
    # Rate Limiting
    RATE_LIMIT_UPLOADS: str = "5/minute"  # Max 5 uploads per minute per user
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache to ensure settings are loaded only once.
    """
    return Settings()


# Create global settings instance
settings = get_settings()


# Ensure temp upload directory exists
def ensure_temp_dir():
    """Ensure temporary upload directory exists."""
    os.makedirs(settings.TEMP_UPLOAD_DIR, exist_ok=True)


ensure_temp_dir()