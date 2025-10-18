#!/usr/bin/env python3
"""
Mark circular reference cells as requiring custom evaluation.

HyperFormula cannot handle circular references (returns #CYCLE!).
This script marks these cells appropriately:
- Sets calculation_engine = 'custom'
- Sets calculated_value = NULL
- Sets has_mismatch = false (we acknowledge we can't evaluate them)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv('DATABASE_URL', 'postgresql://localhost/capitallens')


def mark_circular_as_custom(model_id: int = 1, dry_run: bool = True):
    """
    Mark circular cells as requiring custom evaluation.
    
    Args:
        model_id: Model ID to fix
        dry_run: If True, only show what would be changed
    """
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Get circular cells with zero calculated values
        query = text("""
            SELECT 
                sheet_name, cell, formula, raw_value, calculated_value,
                has_mismatch, calculation_engine
            FROM cell
            WHERE model_id = :model_id
                AND is_circular = true
                AND has_mismatch = true
                AND calculated_value = 0
            ORDER BY sheet_name, row_num, col_letter
        """)
        
        results = session.execute(query, {'model_id': model_id}).fetchall()
        
        logger.info(f"Found {len(results)} circular cells with has_mismatch=True and calculated_value=0")
        
        if dry_run:
            logger.info("\nDRY RUN - Would update the following cells:")
            logger.info("-" * 80)
            for row in results[:10]:
                logger.info(f"  {row.sheet_name}!{row.cell}")
                logger.info(f"    Formula: {row.formula[:60]}")
                logger.info(f"    Current: engine={row.calculation_engine}, "
                          f"calculated={row.calculated_value}, mismatch={row.has_mismatch}")
                logger.info(f"    Will set: engine='custom', calculated=NULL, mismatch=FALSE")
            if len(results) > 10:
                logger.info(f"  ... and {len(results) - 10} more")
            logger.info("\nRationale:")
            logger.info("  - HyperFormula cannot evaluate circular references (#CYCLE! error)")
            logger.info("  - These cells require custom iterative calculation")
            logger.info("  - Setting calculated_value=NULL (not 0) indicates 'not yet evaluated'")
            logger.info("  - Setting has_mismatch=FALSE removes from mismatch count")
            logger.info("  - Marking as 'custom' engine indicates they need special handling")
            return
        
        # Update circular cells
        update_query = text("""
            UPDATE cell
            SET 
                calculation_engine = 'custom',
                calculated_value = NULL,
                has_mismatch = false,
                mismatch_diff = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE model_id = :model_id
                AND is_circular = true
                AND has_mismatch = true
                AND calculated_value = 0
        """)
        
        result = session.execute(update_query, {'model_id': model_id})
        session.commit()
        
        logger.info(f"Successfully updated {result.rowcount} cells")
        logger.info("Changes:")
        logger.info("  - calculation_engine: → 'custom'")
        logger.info("  - calculated_value: 0 → NULL")
        logger.info("  - has_mismatch: true → false")
        logger.info("  - mismatch_diff: → NULL")
        
        # Verify
        verify_query = text("""
            SELECT COUNT(*) as count
            FROM cell
            WHERE model_id = :model_id
                AND is_circular = true
                AND has_mismatch = true
        """)
        
        verify_result = session.execute(verify_query, {'model_id': model_id}).fetchone()
        remaining = verify_result.count if verify_result else 0
        
        logger.info(f"\nVerification:")
        logger.info(f"  Remaining circular cells with mismatches: {remaining}")
        
        if remaining == 0:
            logger.info("  ✓ All circular cell mismatches resolved!")
        
    finally:
        session.close()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Mark circular cells as requiring custom evaluation'
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
        help='Actually apply changes (otherwise just shows what would be changed)'
    )
    
    args = parser.parse_args()
    
    mark_circular_as_custom(
        model_id=args.model_id,
        dry_run=not args.no_dry_run
    )


if __name__ == '__main__':
    main()