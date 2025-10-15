"""
Models router - CRUD operations for imported Excel models.

This module provides endpoints for managing imported models and querying their cells.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from api.config import settings
from api.dependencies import get_db, get_current_user
from api.schemas.model_schema import (
    ModelListResponse, ModelDetail, ModelListItem, ModelDeleteResponse, ModelStatsResponse
)
from api.schemas.cell_schema import CellResponse, CellListResponse, CellStatsResponse
from backend.models.schema import Model, Cell

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix='/models', tags=['models'])


@router.get('', response_model=ModelListResponse)
async def list_models(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by model name"),
    db: Session = Depends(get_db)
):
    """
    List all imported models with pagination.
    
    **Query Parameters:**
    - `page`: Page number (default: 1)
    - `page_size`: Items per page (default: 50, max: 100)
    - `search`: Search by model name (optional)
    
    **Example:**
    ```bash
    curl "http://localhost:8000/api/models?page=1&page_size=20&search=financial"
    ```
    
    **Returns:**
    Paginated list of models ordered by upload date (newest first).
    """
    # Build query
    query = db.query(Model)
    
    # Apply search filter
    if search:
        query = query.filter(Model.name.ilike(f"%{search}%"))
    
    # Get total count
    total = query.count()
    
    # Get page of results
    models = query.order_by(Model.uploaded_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size
    
    # Convert to list items with metadata extraction
    items = [ModelListItem.from_orm_with_metadata(model) for model in models]
    
    return ModelListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items
    )


@router.get('/stats', response_model=ModelStatsResponse)
async def get_models_stats(
    db: Session = Depends(get_db)
):
    """
    Get overall statistics across all models.
    
    **Returns:**
    - Total models
    - Total cells across all models
    - Average cells per model
    - etc.
    
    **Example:**
    ```bash
    curl http://localhost:8000/api/models/stats
    ```
    """
    # Count total models
    total_models = db.query(Model).count()
    
    if total_models == 0:
        return ModelStatsResponse(
            total_models=0,
            total_cells=0,
            total_formulas=0,
            total_circular=0,
            avg_cells_per_model=0.0
        )
    
    # Aggregate statistics
    total_cells = db.query(func.count(Cell.model_id)).scalar() or 0
    
    total_formulas = db.query(func.count(Cell.model_id)).filter(
        Cell.formula.isnot(None)
    ).scalar() or 0
    
    total_circular = db.query(func.count(Cell.model_id)).filter(
        Cell.is_circular == True
    ).scalar() or 0
    
    avg_cells = total_cells / total_models if total_models > 0 else 0.0
    
    return ModelStatsResponse(
        total_models=total_models,
        total_cells=total_cells,
        total_formulas=total_formulas,
        total_circular=total_circular,
        avg_cells_per_model=round(avg_cells, 2)
    )


@router.get('/{model_id}', response_model=ModelDetail)
async def get_model(
    model_id: int,
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific model.
    
    **Returns:**
    - Model metadata
    - Import summary
    - Workbook information
    
    **Example:**
    ```bash
    curl http://localhost:8000/api/models/123
    ```
    """
    model = db.query(Model).filter_by(id=model_id).first()
    
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found"
        )
    
    return ModelDetail.model_validate(model)


@router.get('/{model_id}/cells', response_model=CellListResponse)
async def get_model_cells(
    model_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(100, ge=1, le=1000, description="Items per page"),
    sheet_name: Optional[str] = Query(None, description="Filter by sheet name"),
    has_formula: Optional[bool] = Query(None, description="Filter by formula presence"),
    has_mismatch: Optional[bool] = Query(None, description="Filter by mismatch status"),
    is_circular: Optional[bool] = Query(None, description="Filter by circular reference"),
    cell_type: Optional[str] = Query(None, description="Filter by cell type"),
    db: Session = Depends(get_db)
):
    """
    Get cells for a model with filtering and pagination.
    
    **Query Parameters:**
    - `page`: Page number (default: 1)
    - `page_size`: Items per page (default: 100, max: 1000)
    - `sheet_name`: Filter by specific sheet
    - `has_formula`: Filter cells with formulas
    - `has_mismatch`: Filter cells with mismatches
    - `is_circular`: Filter circular reference cells
    - `cell_type`: Filter by type (value/formula/formula_text)
    
    **Examples:**
    ```bash
    # Get all cells
    curl "http://localhost:8000/api/models/123/cells"
    
    # Get cells with mismatches
    curl "http://localhost:8000/api/models/123/cells?has_mismatch=true"
    
    # Get circular reference cells
    curl "http://localhost:8000/api/models/123/cells?is_circular=true"
    
    # Get cells from specific sheet
    curl "http://localhost:8000/api/models/123/cells?sheet_name=Summary"
    ```
    """
    # Verify model exists
    model = db.query(Model).filter_by(id=model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found"
        )
    
    # Build query
    query = db.query(Cell).filter_by(model_id=model_id)
    
    # Apply filters
    if sheet_name:
        query = query.filter_by(sheet_name=sheet_name)
    
    if has_formula is not None:
        if has_formula:
            query = query.filter(Cell.formula.isnot(None))
        else:
            query = query.filter(Cell.formula.is_(None))
    
    if has_mismatch is not None:
        query = query.filter_by(has_mismatch=has_mismatch)
    
    if is_circular is not None:
        query = query.filter_by(is_circular=is_circular)
    
    if cell_type:
        query = query.filter_by(cell_type=cell_type)
    
    # Get total count
    total = query.count()
    
    # Get page of results
    cells = query.order_by(Cell.sheet_name, Cell.row_num, Cell.col_letter)\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size
    
    return CellListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=[CellResponse.model_validate(cell) for cell in cells]
    )


@router.get('/{model_id}/cells/stats', response_model=CellStatsResponse)
async def get_cell_stats(
    model_id: int,
    db: Session = Depends(get_db)
):
    """
    Get statistics about cells in a model.
    
    **Returns:**
    - Total cells, formula cells, circular cells, etc.
    - Breakdown by sheet
    - Breakdown by calculation engine
    
    **Example:**
    ```bash
    curl http://localhost:8000/api/models/123/cells/stats
    ```
    """
    # Verify model exists
    model = db.query(Model).filter_by(id=model_id).first()
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found"
        )
    
    # Get statistics
    total_cells = db.query(func.count(Cell.model_id)).filter_by(model_id=model_id).scalar()
    
    value_cells = db.query(func.count(Cell.model_id)).filter(
        Cell.model_id == model_id,
        Cell.cell_type == 'value'
    ).scalar()
    
    formula_cells = db.query(func.count(Cell.model_id)).filter(
        Cell.model_id == model_id,
        Cell.cell_type == 'formula'
    ).scalar()
    
    formula_text_cells = db.query(func.count(Cell.model_id)).filter(
        Cell.model_id == model_id,
        Cell.cell_type == 'formula_text'
    ).scalar()
    
    circular_cells = db.query(func.count(Cell.model_id)).filter(
        Cell.model_id == model_id,
        Cell.is_circular == True
    ).scalar()
    
    cells_with_mismatch = db.query(func.count(Cell.model_id)).filter(
        Cell.model_id == model_id,
        Cell.has_mismatch == True
    ).scalar()
    
    null_calculated = db.query(func.count(Cell.model_id)).filter(
        Cell.model_id == model_id,
        Cell.formula.isnot(None),
        Cell.calculated_value.is_(None),
        Cell.calculated_text.is_(None)
    ).scalar()
    
    hyperformula_cells = db.query(func.count(Cell.model_id)).filter(
        Cell.model_id == model_id,
        Cell.calculation_engine == 'hyperformula'
    ).scalar()
    
    custom_engine_cells = db.query(func.count(Cell.model_id)).filter(
        Cell.model_id == model_id,
        Cell.calculation_engine == 'custom'
    ).scalar()
    
    # Get cells by sheet
    cells_by_sheet_query = db.query(
        Cell.sheet_name,
        func.count(Cell.model_id).label('count')
    ).filter_by(model_id=model_id).group_by(Cell.sheet_name).all()
    
    cells_by_sheet = {sheet: count for sheet, count in cells_by_sheet_query}
    
    return CellStatsResponse(
        total_cells=total_cells or 0,
        value_cells=value_cells or 0,
        formula_cells=formula_cells or 0,
        formula_text_cells=formula_text_cells or 0,
        circular_cells=circular_cells or 0,
        cells_with_mismatch=cells_with_mismatch or 0,
        null_calculated=null_calculated or 0,
        hyperformula_cells=hyperformula_cells or 0,
        custom_engine_cells=custom_engine_cells or 0,
        cells_by_sheet=cells_by_sheet
    )


@router.delete('/{model_id}', response_model=ModelDeleteResponse)
async def delete_model(
    model_id: int,
    db: Session = Depends(get_db),
    current_user: str = Depends(get_current_user)
):
    """
    Delete a model and all its cells.
    
    This is a cascading delete that removes:
    - Model record
    - All cell records
    - Associated job records (set to NULL)
    - The stored Excel file (from models/ directory)
    
    **Warning:** This operation cannot be undone.
    
    **Returns:**
    - Number of cells deleted
    - Confirmation message
    
    **Example:**
    ```bash
    curl -X DELETE http://localhost:8000/api/models/123
    ```
    """
    # Find model
    model = db.query(Model).filter_by(id=model_id).first()
    
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found"
        )
    
    # Count cells before deletion
    cell_count = db.query(func.count(Cell.model_id)).filter_by(model_id=model_id).scalar()
    
    # Store file path for deletion
    file_path = model.file_path
    
    # Delete model (cascades to cells)
    db.delete(model)
    db.commit()
    
    # Delete physical file
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info(f"Deleted file: {file_path}")
        except Exception as e:
            logger.warning(f"Could not delete file {file_path}: {e}")
    
    logger.info(f"Model {model_id} deleted by {current_user} ({cell_count} cells)")
    
    return ModelDeleteResponse(
        id=model_id,
        message=f"Model deleted successfully",
        cells_deleted=cell_count or 0
    )