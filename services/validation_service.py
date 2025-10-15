"""
Validation Service - Post-import validation of formula calculations.

This module provides validation functionality to verify that calculated
values match Excel's computed values.
"""

import logging
from typing import Dict, List, Optional, Callable, Any
from sqlalchemy.orm import Session

from backend.models.schema import Model, Cell

logger = logging.getLogger(__name__)

# Default tolerance for validation
DEFAULT_TOLERANCE = 1e-6


class ValidationService:
    """
    Framework-agnostic validation service.
    
    Validates all formula cells by comparing calculated values against
    Excel's computed values (raw_value/raw_text).
    """
    
    def __init__(
        self,
        db_session: Session,
        progress_callback: Optional[Callable[[str, float, str], None]] = None,
        tolerance: float = DEFAULT_TOLERANCE
    ):
        """
        Initialize validation service.
        
        Args:
            db_session: SQLAlchemy database session
            progress_callback: Optional callback for progress updates
                              Signature: callback(stage: str, percent: float, message: str)
            tolerance: Tolerance for numeric comparison (default: 1e-6)
        """
        self.session = db_session
        self.progress_callback = progress_callback or (lambda *args: None)
        self.tolerance = tolerance
    
    def _emit_progress(self, stage: str, percent: float, message: str):
        """Emit progress update via callback."""
        self.progress_callback(stage, percent, message)
        logger.info(f"Validation progress: {stage} ({percent:.1f}%) - {message}")
    
    def validate_model(self, model_id: int) -> Dict[str, Any]:
        """
        Validate all formula cells in a model.
        
        Args:
            model_id: Model ID to validate
        
        Returns:
            Validation report dictionary with:
            {
                'status': 'passed' | 'failed' | 'partial',
                'total': int,
                'matches': int,
                'mismatches': int,
                'errors': int,
                'null_calculated': int,
                'tolerance': float,
                'mismatch_cells': [...]
            }
        """
        logger.info(f"Starting validation for model {model_id}")
        self._emit_progress('starting', 0, 'Initializing validation...')
        
        # Check model exists
        model = self.session.query(Model).filter_by(id=model_id).first()
        if not model:
            logger.error(f"Model {model_id} not found")
            return {
                'status': 'error',
                'error': f"Model {model_id} not found"
            }
        
        # Get all formula cells
        self._emit_progress('loading', 10, 'Loading formula cells...')
        formula_cells = self.session.query(Cell).filter(
            Cell.model_id == model_id,
            Cell.cell_type.in_(['formula', 'formula_text'])
        ).all()
        
        total = len(formula_cells)
        logger.info(f"Found {total} formula cells to validate")
        
        if total == 0:
            return {
                'status': 'passed',
                'total': 0,
                'matches': 0,
                'mismatches': 0,
                'errors': 0,
                'null_calculated': 0,
                'tolerance': self.tolerance,
                'mismatch_cells': []
            }
        
        # Validation counters
        matches = 0
        mismatches = 0
        errors = 0
        null_calculated = 0
        mismatch_cells = []
        
        # Validate each cell
        for idx, cell in enumerate(formula_cells):
            # Update progress
            if idx % 50 == 0:
                progress = 10 + (80 * (idx / total))
                self._emit_progress('validating', progress, 
                                  f"Validating cell {idx}/{total}")
            
            try:
                result = self._validate_cell(cell)
                
                if result['status'] == 'match':
                    matches += 1
                elif result['status'] == 'mismatch':
                    mismatches += 1
                    mismatch_cells.append({
                        'cell_ref': f"{cell.sheet_name}!{cell.cell}",
                        'formula': cell.formula,
                        'expected': result.get('expected'),
                        'actual': result.get('actual'),
                        'diff': result.get('diff'),
                        'type': result.get('type')
                    })
                elif result['status'] == 'null_calculated':
                    null_calculated += 1
                    # Treat NULL as error
                    errors += 1
                    mismatch_cells.append({
                        'cell_ref': f"{cell.sheet_name}!{cell.cell}",
                        'formula': cell.formula,
                        'expected': result.get('expected'),
                        'actual': None,
                        'error': 'Calculated value is NULL'
                    })
                elif result['status'] == 'error':
                    errors += 1
                    mismatch_cells.append({
                        'cell_ref': f"{cell.sheet_name}!{cell.cell}",
                        'formula': cell.formula,
                        'error': result.get('error')
                    })
                    
            except Exception as e:
                logger.error(f"Error validating {cell.sheet_name}!{cell.cell}: {e}")
                errors += 1
        
        # Determine overall status
        self._emit_progress('finalizing', 95, 'Finalizing validation report...')
        
        if mismatches == 0 and errors == 0:
            status = 'passed'
        elif mismatches > 0 or errors > 0:
            if matches > 0:
                status = 'partial'
            else:
                status = 'failed'
        else:
            status = 'unknown'
        
        report = {
            'status': status,
            'total': total,
            'matches': matches,
            'mismatches': mismatches,
            'errors': errors,
            'null_calculated': null_calculated,
            'tolerance': self.tolerance,
            'mismatch_cells': mismatch_cells[:100],  # Limit to first 100
            'mismatch_summary': {
                'total_mismatches': len(mismatch_cells),
                'shown': min(len(mismatch_cells), 100)
            }
        }
        
        self._emit_progress('complete', 100, 'Validation complete')
        logger.info(f"Validation complete: {status} ({matches} matches, {mismatches} mismatches, {errors} errors)")
        
        return report
    
    def _validate_cell(self, cell: Cell) -> Dict[str, Any]:
        """
        Validate a single cell.
        
        Args:
            cell: Cell object to validate
        
        Returns:
            Dictionary with validation result:
            {
                'status': 'match' | 'mismatch' | 'null_calculated' | 'error',
                'expected': value (if applicable),
                'actual': value (if applicable),
                'diff': float (if applicable),
                'type': 'numeric' | 'text' (if applicable),
                'error': str (if error)
            }
        """
        try:
            if cell.cell_type == 'formula_text':
                # Validate text formula
                return self._validate_text_cell(cell)
            elif cell.cell_type == 'formula':
                # Validate numeric formula
                return self._validate_numeric_cell(cell)
            else:
                # Not a formula cell
                return {
                    'status': 'error',
                    'error': f"Cell type {cell.cell_type} is not a formula"
                }
                
        except Exception as e:
            logger.error(f"Error in _validate_cell for {cell.sheet_name}!{cell.cell}: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _validate_numeric_cell(self, cell: Cell) -> Dict[str, Any]:
        """
        Validate a numeric formula cell.
        
        Compares calculated_value against raw_value (Excel's computed value).
        """
        # Check if calculated_value is NULL
        if cell.calculated_value is None:
            return {
                'status': 'null_calculated',
                'expected': float(cell.raw_value) if cell.raw_value is not None else None,
                'actual': None
            }
        
        # Check if raw_value is available for comparison
        if cell.raw_value is None:
            return {
                'status': 'error',
                'error': 'No raw_value available for comparison'
            }
        
        # Compare values
        expected = float(cell.raw_value)
        actual = float(cell.calculated_value)
        diff = abs(expected - actual)
        
        if diff <= self.tolerance:
            return {
                'status': 'match',
                'expected': expected,
                'actual': actual,
                'diff': diff,
                'type': 'numeric'
            }
        else:
            return {
                'status': 'mismatch',
                'expected': expected,
                'actual': actual,
                'diff': diff,
                'type': 'numeric'
            }
    
    def _validate_text_cell(self, cell: Cell) -> Dict[str, Any]:
        """
        Validate a text formula cell.
        
        Compares calculated_text against raw_text (Excel's computed text).
        """
        # Check if calculated_text is NULL
        if cell.calculated_text is None:
            return {
                'status': 'null_calculated',
                'expected': cell.raw_text,
                'actual': None
            }
        
        # Check if raw_text is available for comparison
        if cell.raw_text is None:
            return {
                'status': 'error',
                'error': 'No raw_text available for comparison'
            }
        
        # Compare text values (exact match required)
        if cell.calculated_text == cell.raw_text:
            return {
                'status': 'match',
                'expected': cell.raw_text,
                'actual': cell.calculated_text,
                'diff': 0,
                'type': 'text'
            }
        else:
            # Calculate character difference
            len_diff = abs(len(cell.calculated_text) - len(cell.raw_text))
            return {
                'status': 'mismatch',
                'expected': cell.raw_text,
                'actual': cell.calculated_text,
                'diff': len_diff,
                'type': 'text'
            }
    
    def get_mismatches(self, model_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get cells with mismatches for a model.
        
        Args:
            model_id: Model ID
            limit: Maximum number of results
        
        Returns:
            List of mismatch dictionaries
        """
        cells = self.session.query(Cell).filter(
            Cell.model_id == model_id,
            Cell.has_mismatch == True
        ).limit(limit).all()
        
        mismatches = []
        for cell in cells:
            mismatches.append({
                'cell_ref': f"{cell.sheet_name}!{cell.cell}",
                'formula': cell.formula,
                'raw_value': float(cell.raw_value) if cell.raw_value else None,
                'calculated_value': float(cell.calculated_value) if cell.calculated_value else None,
                'raw_text': cell.raw_text,
                'calculated_text': cell.calculated_text,
                'mismatch_diff': float(cell.mismatch_diff) if cell.mismatch_diff else None,
                'cell_type': cell.cell_type,
                'is_circular': cell.is_circular
            })
        
        return mismatches
    
    def get_null_calculated_cells(self, model_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get cells where calculated_value is NULL but formula exists.
        
        Args:
            model_id: Model ID
            limit: Maximum number of results
        
        Returns:
            List of cell dictionaries
        """
        cells = self.session.query(Cell).filter(
            Cell.model_id == model_id,
            Cell.formula.isnot(None),
            Cell.calculated_value.is_(None),
            Cell.calculated_text.is_(None)
        ).limit(limit).all()
        
        null_cells = []
        for cell in cells:
            null_cells.append({
                'cell_ref': f"{cell.sheet_name}!{cell.cell}",
                'formula': cell.formula,
                'raw_value': float(cell.raw_value) if cell.raw_value else None,
                'raw_text': cell.raw_text,
                'cell_type': cell.cell_type,
                'is_circular': cell.is_circular,
                'calculation_engine': cell.calculation_engine
            })
        
        return null_cells
    
    def get_validation_summary(self, model_id: int) -> Dict[str, Any]:
        """
        Get quick validation summary without full re-validation.
        
        Args:
            model_id: Model ID
        
        Returns:
            Summary dictionary
        """
        # Count formula cells
        total_formulas = self.session.query(Cell).filter(
            Cell.model_id == model_id,
            Cell.cell_type.in_(['formula', 'formula_text'])
        ).count()
        
        # Count mismatches
        mismatches = self.session.query(Cell).filter(
            Cell.model_id == model_id,
            Cell.has_mismatch == True
        ).count()
        
        # Count NULL calculated values
        null_calculated = self.session.query(Cell).filter(
            Cell.model_id == model_id,
            Cell.formula.isnot(None),
            Cell.calculated_value.is_(None),
            Cell.calculated_text.is_(None)
        ).count()
        
        # Calculate matches
        matches = total_formulas - mismatches - null_calculated
        
        # Determine status
        if mismatches == 0 and null_calculated == 0:
            status = 'passed'
        elif matches > 0:
            status = 'partial'
        else:
            status = 'failed'
        
        return {
            'status': status,
            'total': total_formulas,
            'matches': matches,
            'mismatches': mismatches,
            'null_calculated': null_calculated,
            'tolerance': self.tolerance
        }