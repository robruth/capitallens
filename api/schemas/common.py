"""
Common Pydantic schemas used across the API.

This module contains shared schemas for pagination, errors, and
other common response patterns.
"""

from typing import Any, Dict, List, Optional, Generic, TypeVar
from pydantic import BaseModel, Field
from datetime import datetime

# Type variable for generic pagination
T = TypeVar('T')


class ErrorResponse(BaseModel):
    """Standard error response format."""
    
    error: str = Field(..., description="Error message")
    detail: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")
    path: Optional[str] = Field(None, description="Request path that caused the error")
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "File not found",
                "detail": {"file_id": 123},
                "timestamp": "2025-10-15T12:00:00Z",
                "path": "/api/models/123"
            }
        }


class PaginationParams(BaseModel):
    """Standard pagination parameters."""
    
    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(50, ge=1, le=1000, description="Number of items per page")
    
    @property
    def offset(self) -> int:
        """Calculate offset for database query."""
        return (self.page - 1) * self.page_size
    
    @property
    def limit(self) -> int:
        """Get limit for database query."""
        return self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""
    
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    items: List[T] = Field(..., description="Items in current page")
    
    @classmethod
    def create(cls, items: List[T], total: int, page: int, page_size: int):
        """
        Create paginated response.
        
        Args:
            items: List of items for current page
            total: Total number of items
            page: Current page number
            page_size: Items per page
        
        Returns:
            PaginatedResponse instance
        """
        total_pages = (total + page_size - 1) // page_size  # Ceiling division
        
        return cls(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            items=items
        )


class SuccessResponse(BaseModel):
    """Standard success response."""
    
    success: bool = Field(True, description="Operation success flag")
    message: str = Field(..., description="Success message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional data")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {"id": 123}
            }
        }


class HealthCheckResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Health check timestamp")
    version: str = Field(..., description="API version")
    database: str = Field(..., description="Database connection status")
    redis: str = Field(..., description="Redis connection status")
    celery: str = Field(..., description="Celery worker status")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2025-10-15T12:00:00Z",
                "version": "1.0.0",
                "database": "connected",
                "redis": "connected",
                "celery": "active"
            }
        }