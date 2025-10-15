"""
Model-related Pydantic schemas.

This module contains schemas for Excel model (workbook) management.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ModelListItem(BaseModel):
    """Model list item for paginated list responses."""
    
    id: int = Field(..., description="Model ID")
    name: str = Field(..., description="User-friendly model name")
    original_filename: Optional[str] = Field(None, description="Original Excel filename")
    file_hash: str = Field(..., description="SHA256 file hash")
    uploaded_at: datetime = Field(..., description="Upload timestamp")
    
    # Metadata summary
    sheet_count: Optional[int] = Field(None, description="Number of sheets in workbook")
    total_cells: Optional[int] = Field(None, description="Total cells imported")
    formula_cells: Optional[int] = Field(None, description="Formula cells imported")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 123,
                "name": "Q4 2025 Financial Model",
                "original_filename": "dcmodel_template.xlsx",
                "file_hash": "a1b2c3d4e5f6...",
                "uploaded_at": "2025-10-15T12:00:00Z",
                "sheet_count": 2,
                "total_cells": 758,
                "formula_cells": 617
            }
        }
    
    @classmethod
    def from_orm_with_metadata(cls, model):
        """Create from ORM model with extracted metadata."""
        metadata = model.workbook_metadata or {}
        
        return cls(
            id=model.id,
            name=model.name,
            original_filename=model.original_filename,
            file_hash=model.file_hash,
            uploaded_at=model.uploaded_at,
            sheet_count=metadata.get('sheet_count'),
            total_cells=metadata.get('total_cells'),
            formula_cells=metadata.get('formula_cells')
        )


class ModelDetail(BaseModel):
    """Detailed model information."""
    
    id: int = Field(..., description="Model ID")
    name: str = Field(..., description="User-friendly model name")
    original_filename: Optional[str] = Field(None, description="Original Excel filename")
    file_path: Optional[str] = Field(None, description="Path to stored file")
    file_hash: str = Field(..., description="SHA256 file hash")
    uploaded_at: datetime = Field(..., description="Upload timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # Detailed metadata
    workbook_metadata: Dict[str, Any] = Field(..., description="Workbook metadata")
    import_summary: Dict[str, Any] = Field(..., description="Import statistics")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 123,
                "name": "Q4 2025 Financial Model",
                "original_filename": "dcmodel_template.xlsx",
                "file_path": "models/a1b2c3d4e5f6.xlsx",
                "file_hash": "a1b2c3d4e5f67890...",
                "uploaded_at": "2025-10-15T12:00:00Z",
                "updated_at": "2025-10-15T12:00:30Z",
                "workbook_metadata": {
                    "sheets": ["Summary", "Monthly"],
                    "sheet_count": 2,
                    "total_cells": 758,
                    "formula_cells": 617
                },
                "import_summary": {
                    "circular_references": 122,
                    "exact_matches": 610,
                    "mismatches": 2
                }
            }
        }


class ModelCreateRequest(BaseModel):
    """Request to create a model (for future use)."""
    
    name: str = Field(..., min_length=1, max_length=255, description="Model name")
    description: Optional[str] = Field(None, description="Optional description")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Q4 2025 Financial Model",
                "description": "Quarterly financial projections"
            }
        }


class ModelListResponse(BaseModel):
    """Paginated model list response."""
    
    total: int = Field(..., description="Total number of models")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    items: list[ModelListItem] = Field(..., description="Models in current page")


class ModelStatsResponse(BaseModel):
    """Model statistics."""
    
    total_models: int = Field(..., description="Total models")
    total_cells: int = Field(..., description="Total cells across all models")
    total_formulas: int = Field(..., description="Total formula cells")
    total_circular: int = Field(..., description="Total circular reference cells")
    avg_cells_per_model: float = Field(..., description="Average cells per model")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_models": 25,
                "total_cells": 15000,
                "total_formulas": 12000,
                "total_circular": 500,
                "avg_cells_per_model": 600.0
            }
        }


class ModelDeleteResponse(BaseModel):
    """Response when a model is deleted."""
    
    id: int = Field(..., description="Deleted model ID")
    message: str = Field(..., description="Success message")
    cells_deleted: int = Field(..., description="Number of cells deleted")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 123,
                "message": "Model deleted successfully",
                "cells_deleted": 758
            }
        }