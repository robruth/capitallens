"""
Import-related Pydantic schemas.

This module contains schemas for Excel file import requests and responses.
"""

from typing import Optional
from pydantic import BaseModel, Field
from api.schemas.job_schema import JobCreateResponse


class ImportRequest(BaseModel):
    """Request schema for file import (form data)."""
    
    model_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="User-friendly name for the model"
    )
    run_validation: bool = Field(
        default=False,
        description="Whether to run post-import validation",
        alias="validate"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "model_name": "Q4 2025 Financial Model",
                "validate": True
            }
        }


class ImportStartResponse(JobCreateResponse):
    """
    Response when import is initiated.
    
    Extends JobCreateResponse with import-specific messages.
    """
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "abc-123-def-456",
                "message": "Excel import job started",
                "status_url": "/api/import/job/abc-123-def-456",
                "websocket_url": "/ws/import/abc-123-def-456"
            }
        }


class ImportResultResponse(BaseModel):
    """Detailed import results."""
    
    model_id: int = Field(..., description="ID of imported model")
    stats: dict = Field(..., description="Import statistics")
    validation_results: Optional[dict] = Field(None, description="Validation results if requested")
    errors: list = Field(default_factory=list, description="List of errors encountered")
    duplicate: bool = Field(False, description="Whether file was already imported")
    
    class Config:
        json_schema_extra = {
            "example": {
                "model_id": 123,
                "stats": {
                    "total_cells": 758,
                    "formula_cells": 617,
                    "circular_references": 122,
                    "exact_matches": 610,
                    "mismatches": 2
                },
                "validation_results": None,
                "errors": [],
                "duplicate": False
            }
        }