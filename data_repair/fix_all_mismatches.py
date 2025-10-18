#!/usr/bin/env python3
"""
Comprehensive fix for all calculation mismatches.

This script:
1. Marks circular cells as 'custom' (HyperFormula can't evaluate them)
2. Reports on any remaining mismatches
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


def fix_all_mismatches(model_id: int = 1):
    """Fix all calculation mismatches for a model."""
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        logger.info(f"Analyzing mismatches for model {model_id}...")
        
        # Get mismatch statistics
        stats_query = text("""
            SELECT 
                is_circular,
                calculation_engine,
                COUNT(*) as count
            FROM cell
            WHERE model_id = :model_id
                AND has_mismatch = true
            GROUP BY is_circular, calculation_engine
            ORDER BY is_circular, calculation_engine
        """)
        
        stats = session.execute(stats_query, {'model_id': model_id}).fetchall()
        
        logger.info("Current mismatch breakdown:")
        total_mismatches = 0
        for row in stats:
            logger.info(f"  {'Circular' if row.is_circular else 'Non-circular'}, "
                       f"engine={row.calculation_engine}: {row.count}")
            total_mismatches += row.count
        
        logger.info(f"Total mismatches: {total_mismatches}")
        
        if total_mismatches == 0:
            logger.info("✓ No mismatches found!")
            return
        
        # Fix circular cells (mark as custom with NULL calculated_value)
        circular_query = text("""
            SELECT COUNT(*) as count
            FROM cell
            WHERE model_id = :model_id
                AND is_circular = true
                AND has_mismatch = true
        """)
        
        circular_count = session.execute(circular_query, {'model_id': model_id}).fetchone().count
        
        if circular_count > 0:
            logger.info(f"\nFixing {circular_count} circular reference mismatches...")
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
            """)
            
            result = session.execute(update_query, {'model_id': model_id})
            session.commit()
            logger.info(f"✓ Marked {result.rowcount} circular cells as 'custom'")
        
        # Check remaining mismatches
        remaining_query = text("""
            SELECT 
                sheet_name, cell, formula, raw_value, calculated_value,
                is_circular, calculation_engine
            FROM cell
            WHERE model_id = :model_id
                AND has_mismatch = true
            ORDER BY sheet_name, row_num, col_letter
            LIMIT 10
        """)
        
        remaining = session.execute(remaining_query, {'model_id': model_id}).fetchall()
        
        if remaining:
            logger.warning(f"\n⚠ {len(remaining)} mismatches remain (showing first 10):")
            for row in remaining:
                logger.warning(f"  {row.sheet_name}!{row.cell}")
                logger.warning(f"    Formula: {row.formula[:60] if row.formula else 'N/A'}")
                logger.warning(f"    Raw: {row.raw_value}, Calculated: {row.calculated_value}")
                logger.warning(f"    Circular: {row.is_circular}, Engine: {row.calculation_engine}")
        else:
            logger.info("\n✓ All mismatches resolved!")
        
        # Final summary
        final_count_query = text("""
            SELECT COUNT(*) as count
            FROM cell
            WHERE model_id = :model_id
                AND has_mismatch = true
        """)
        
        final_count = session.execute(final_count_query, {'model_id': model_id}).fetchone().count
        
        logger.info(f"\nFinal mismatch count: {final_count}")
        
    finally:
        session.close()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Fix all calculation mismatches'
    )
    parser.add_argument(
        '--model-id',
        type=int,
        default=1,
        help='Model ID to fix (default: 1)'
    )
    
    args = parser.parse_args()
    
    fix_all_mismatches(model_id=args.model_id)


if __name__ == '__main__':
    main()