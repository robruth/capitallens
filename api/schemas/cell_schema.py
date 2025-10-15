"""
Cell-related Pydantic schemas.

This module contains schemas for individual cell data.
"""

from typing import Optional, List, Dict
from decimal import Decimal
from pydantic import BaseModel, Field
from datetime import datetime


class CellResponse(BaseModel):
    """Cell data response schema."""
    
    # Identification
    sheet_name: str = Field(..., description="Worksheet name")
    cell: str = Field(..., description="Cell address (e.g., A1, B24)")
    row_num: int = Field(..., description="Row number")
    col_letter: str = Field(..., description="Column letter(s)")
    
    # Cell content
    cell_type: str = Field(..., description="Cell type: value, formula, formula_text")
    raw_value: Optional[Decimal] = Field(None, description="Excel's computed numeric value")
    raw_text: Optional[str] = Field(None, description="Excel's computed text value")
    formula: Optional[str] = Field(None, description="Formula text")
    data_type: str = Field(..., description="Data type: number, text, date, boolean")
    
    # Calculation results
    calculated_value: Optional[Decimal] = Field(None, description="Our calculated numeric result")
    calculated_text: Optional[str] = Field(None, description="Our calculated text result")
    calculation_engine: str = Field(..., description="Engine used: none, hyperformula, custom")
    
    # Dependencies and validation
    depends_on: List[str] = Field(default_factory=list, description="Cell dependencies")
    is_circular: bool = Field(..., description="Part of circular reference")
    has_validation: bool = Field(..., description="Has data validation")
    
    # Validation results
    has_mismatch: bool = Field(..., description="Calculated value differs from raw value")
    mismatch_diff: Optional[Decimal] = Field(None, description="Absolute difference if mismatch")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "sheet_name": "Summary",
                "cell": "B24",
                "row_num": 24,
                "col_letter": "B",
                "cell_type": "formula",
                "raw_value": 100.50,
                "raw_text": None,
                "formula": "=SUM(B2:B23)",
                "data_type": "number",
                "calculated_value": 100.50,
                "calculated_text": None,
                "calculation_engine": "hyperformula",
                "depends_on": ["Summary!B2", "Summary!B23"],
                "is_circular": False,
                "has_validation": False,
                "has_mismatch": False,
                "mismatch_diff": None
            }
        }


class CellListResponse(BaseModel):
    """Paginated cell list response."""
    
    total: int = Field(..., description="Total number of cells")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    items: List[CellResponse] = Field(..., description="Cells in current page")


class CellFilterParams(BaseModel):
    """Query parameters for filtering cells."""
    
    sheet_name: Optional[str] = Field(None, description="Filter by sheet name")
    has_formula: Optional[bool] = Field(None, description="Filter by presence of formula")
    has_mismatch: Optional[bool] = Field(None, description="Filter by mismatch status")
    is_circular: Optional[bool] = Field(None, description="Filter by circular reference status")
    cell_type: Optional[str] = Field(None, description="Filter by cell type")
    calculation_engine: Optional[str] = Field(None, description="Filter by calculation engine")


class CellStatsResponse(BaseModel):
    """Cell statistics for a model."""
    
    total_cells: int = Field(..., description="Total cells")
    value_cells: int = Field(..., description="Value cells (no formula)")
    formula_cells: int = Field(..., description="Formula cells")
    formula_text_cells: int = Field(..., description="Text formula cells")
    circular_cells: int = Field(..., description="Circular reference cells")
    cells_with_mismatch: int = Field(..., description="Cells with mismatches")
    null_calculated: int = Field(..., description="Cells with NULL calculated values")
    
    # By engine
    hyperformula_cells: int = Field(..., description="Cells using HyperFormula")
    custom_engine_cells: int = Field(..., description="Cells using custom engine")
    
    # By sheet
    cells_by_sheet: Dict[str, int] = Field(..., description="Cell count by sheet")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_cells": 758,
                "value_cells": 141,
                "formula_cells": 617,
                "formula_text_cells": 0,
                "circular_cells": 122,
                "cells_with_mismatch": 2,
                "null_calculated": 0,
                "hyperformula_cells": 495,
                "custom_engine_cells": 122,
                "cells_by_sheet": {
                    "Summary": 400,
                    "Monthly": 358
                }
            }
        }