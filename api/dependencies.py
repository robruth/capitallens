"""
Dependency injection utilities for FastAPI.

This module provides reusable dependencies for database sessions,
authentication, and other cross-cutting concerns.
"""

import logging
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from fastapi import Depends, HTTPException, Header, status

from api.config import settings

logger = logging.getLogger(__name__)

# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=settings.DB_POOL_PRE_PING,
    echo=settings.DEBUG
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Get database session dependency.
    
    Yields database session and ensures it's closed after use.
    
    Usage:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            # Use db session
            pass
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_api_key(
    x_api_key: str = Header(None, alias=settings.API_KEY_HEADER)
) -> str:
    """
    Validate API key from header.
    
    Args:
        x_api_key: API key from request header
    
    Returns:
        Validated API key
    
    Raises:
        HTTPException: If API key is invalid or missing
    
    Usage:
        @app.get("/endpoint")
        def endpoint(api_key: str = Depends(get_api_key)):
            # API key is validated
            pass
    """
    if not settings.ENABLE_API_KEY_AUTH:
        # API key auth disabled - allow all requests
        return "public"
    
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    # TODO: Validate API key against database
    # For now, accept any non-empty key
    # In production, implement proper validation:
    # valid_key = db.query(APIKey).filter_by(key=x_api_key, active=True).first()
    # if not valid_key:
    #     raise HTTPException(...)
    
    return x_api_key


def get_current_user(api_key: str = Depends(get_api_key)) -> str:
    """
    Get current user from API key.
    
    Args:
        api_key: Validated API key
    
    Returns:
        User identifier (for now, returns api_key)
    
    Usage:
        @app.get("/endpoint")
        def endpoint(user: str = Depends(get_current_user)):
            # User is authenticated
            pass
    """
    # TODO: Look up user from API key in database
    # For now, use API key as user identifier
    return api_key


def verify_file_size(file_size: int) -> bool:
    """
    Verify uploaded file size is within limit.
    
    Args:
        file_size: File size in bytes
    
    Returns:
        True if size is acceptable
    
    Raises:
        HTTPException: If file is too large
    """
    max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    
    if file_size > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size ({file_size / 1024 / 1024:.1f} MB) exceeds maximum allowed "
                   f"({settings.MAX_FILE_SIZE_MB} MB)"
        )
    
    return True


def verify_file_extension(filename: str) -> bool:
    """
    Verify file has allowed extension.
    
    Args:
        filename: Name of uploaded file
    
    Returns:
        True if extension is allowed
    
    Raises:
        HTTPException: If extension is not allowed
    """
    from pathlib import Path
    
    ext = Path(filename).suffix.lower()
    
    if ext not in [e.lower() for e in settings.ALLOWED_EXTENSIONS]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' not allowed. "
                   f"Allowed extensions: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    
    return True