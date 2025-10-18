#!/usr/bin/env python3
"""
Fix circular reference calculations that evaluated to 0.

This script re-evaluates circular cells using the corrected HyperFormula logic.
"""

import os
import sys
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import logging

from services.excel_import_service import ExcelImportService
from services.formula_service import FormulaParser

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv('DATABASE_URL', 'postgresql://localhost/capitallens')


def fix_circular_cells(model_id: int = 1, dry_run: bool = True):
    """
    Re-evaluate circular cells that have calculated_value = 0.
    
    Args:
        model_id: Model ID to fix
        dry_run: If True, only show what would be fixed without making changes
    """
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Get all cells for this model to build complete context
        logger.info(f"Loading all cells for model {model_id}...")
        query = text("""
            SELECT 
                sheet_name, cell, row_num, col_letter, cell_type,
                raw_value, raw_text, formula, data_type, depends_on,
                is_circular, calculation_engine
            FROM cell
            WHERE model_id = :model_id
            ORDER BY sheet_name, row_num, col_letter
        """)
        
        all_cells = session.execute(query, {'model_id': model_id}).fetchall()
        logger.info(f"Loaded {len(all_cells)} cells")
        
        # Convert to cell data format expected by ExcelImportService
        cells_data = []
        for row in all_cells:
            cell_data = {
                'sheet_name': row.sheet_name,
                'cell': row.cell,
                'row_num': row.row_num,
                'col_letter': row.col_letter,
                'cell_type': row.cell_type,
                'raw_value': float(row.raw_value) if row.raw_value else None,
                'raw_text': row.raw_text,
                'formula': row.formula,
                'data_type': row.data_type,
                'depends_on': row.depends_on or [],
                'is_circular': row.is_circular or False
            }
            cells_data.append(cell_data)
        
        # Get circular cells with zero calculated values
        circular_zero_query = text("""
            SELECT 
                sheet_name, cell, row_num, col_letter, cell_type,
                raw_value, formula, depends_on
            FROM cell
            WHERE model_id = :model_id
                AND is_circular = true
                AND (calculated_value = 0 OR calculated_value IS NULL)
                AND formula IS NOT NULL
            ORDER BY sheet_name, row_num, col_letter
        """)
        
        circular_cells_to_fix = session.execute(
            circular_zero_query, 
            {'model_id': model_id}
        ).fetchall()
        
        logger.info(f"Found {len(circular_cells_to_fix)} circular cells to fix")
        
        if not circular_cells_to_fix:
            logger.info("No circular cells need fixing")
            return
        
        if dry_run:
            logger.info("\nDRY RUN - Would fix the following cells:")
            logger.info("-" * 80)
            for row in circular_cells_to_fix[:10]:
                logger.info(f"  {row.sheet_name}!{row.cell}: {row.formula[:60]}")
                logger.info(f"    Raw value: {row.raw_value}")
            if len(circular_cells_to_fix) > 10:
                logger.info(f"  ... and {len(circular_cells_to_fix) - 10} more")
            return
        
        # Initialize ExcelImportService
        logger.info("Initializing formula evaluation service...")
        import_service = ExcelImportService(session)
        
        # Build HyperFormula sheets with ALL cells
        logger.info("Building HyperFormula context...")
        sheets_data = import_service._build_hyperformula_sheets(cells_data)
        
        # Extract just the circular cells that need fixing
        circular_cells = [c for c in cells_data if c.get('is_circular') and c.get('formula')]
        
        # Build cell lookup
        cell_lookup = {}
        for cell in cells_data:
            cell_ref = f"{cell['sheet_name']}!{cell['cell']}"
            cell_lookup[cell_ref] = cell
        
        # Evaluate circular cells
        logger.info(f"Evaluating {len(circular_cells)} circular formulas...")
        cache = {}
        import_service._evaluate_circular_cells_hyperformula(
            circular_cells,
            sheets_data,
            cell_lookup,
            cache
        )
        
        # Update database with new calculated values
        logger.info("Updating database...")
        updated_count = 0
        
        for cell in circular_cells:
            cell_ref = f"{cell['sheet_name']}!{cell['cell']}"
            if cell_ref in cache or cell.get('calculated_value') is not None:
                calculated_value = cache.get(cell_ref) or cell.get('calculated_value')
                
                # Only update if we have a non-zero value
                if calculated_value is not None and calculated_value != 0:
                    update_query = text("""
                        UPDATE cell
                        SET 
                            calculated_value = :calculated_value,
                            has_mismatch = CASE
                                WHEN raw_value IS NOT NULL AND 
                                     ABS(:calculated_value - raw_value) > :tolerance
                                THEN true
                                ELSE false
                            END,
                            mismatch_diff = CASE
                                WHEN raw_value IS NOT NULL
                                THEN ABS(:calculated_value - raw_value)
                                ELSE NULL
                            END,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE model_id = :model_id
                            AND sheet_name = :sheet_name
                            AND cell = :cell
                    """)
                    
                    session.execute(update_query, {
                        'model_id': model_id,
                        'sheet_name': cell['sheet_name'],
                        'cell': cell['cell'],
                        'calculated_value': calculated_value,
                        'tolerance': 1e-6
                    })
                    updated_count += 1
                    
                    logger.debug(f"Updated {cell['sheet_name']}!{cell['cell']}: "
                               f"{calculated_value:.2f} (raw: {cell.get('raw_value', 'N/A')})")
        
        session.commit()
        logger.info(f"Successfully updated {updated_count} cells")
        
        # Verify results
        verify_query = text("""
            SELECT COUNT(*) as count
            FROM cell
            WHERE model_id = :model_id
                AND is_circular = true
                AND has_mismatch = true
                AND calculated_value = 0
        """)
        
        result = session.execute(verify_query, {'model_id': model_id}).fetchone()
        remaining = result.count if result else 0
        
        logger.info(f"\nVerification:")
        logger.info(f"  Remaining circular cells with zero/mismatch: {remaining}")
        
        if remaining == 0:
            logger.info("  ✓ All circular cells successfully fixed!")
        else:
            logger.warning(f"  ⚠ Still have {remaining} cells with issues")
    
    finally:
        session.close()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Fix circular reference calculations'
    )
    parser.add_argument(
        '--model-id',
        type=int,
        default=1,
        help='Model ID to fix (default: 1)'
    )
    parser.add_argument(
        '--no-dry-run',
        action='store_true',
        help='Actually apply fixes (otherwise just shows what would be fixed)'
    )
    
    args = parser.parse_args()
    
    fix_circular_cells(
        model_id=args.model_id,
        dry_run=not args.no_dry_run
    )


if __name__ == '__main__':
    main()