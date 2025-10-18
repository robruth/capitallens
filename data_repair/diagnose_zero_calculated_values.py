#!/usr/bin/env python3
"""
Diagnose cells with zero calculated values and mismatches.

This script examines cells where:
- has_mismatch = True
- calculated_value = 0
- model_id = 1

Determines if they should have custom formulas or if there's a calculation bug.
"""

import os
import sys
from decimal import Decimal
from typing import Dict, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv('DATABASE_URL', 'postgresql://localhost/capitallens')


def diagnose_zero_calculated_values(model_id: int = 1):
    """
    Diagnose cells with calculated_value = 0 and has_mismatch = True.
    
    Args:
        model_id: Model ID to examine
    """
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Query cells with the issue
        query = text("""
            SELECT 
                sheet_name,
                cell,
                cell_type,
                raw_value,
                formula,
                calculated_value,
                calculation_engine,
                is_circular,
                data_type,
                mismatch_diff,
                converted_formula
            FROM cell
            WHERE model_id = :model_id
                AND has_mismatch = true
                AND calculated_value = 0
            ORDER BY sheet_name, row_num, col_letter
        """)
        
        results = session.execute(query, {'model_id': model_id}).fetchall()
        
        print(f"Found {len(results)} cells with calculated_value=0 and mismatches\n")
        print("=" * 100)
        
        # Categorize issues
        categories = {
            'custom_functions': [],
            'empty_formulas': [],
            'circular': [],
            'hyperformula_errors': [],
            'legitimate_zeros': [],
            'other': []
        }
        
        for row in results:
            cell_info = {
                'sheet': row.sheet_name,
                'cell': row.cell,
                'cell_type': row.cell_type,
                'raw_value': float(row.raw_value) if row.raw_value else None,
                'formula': row.formula,
                'calculated_value': float(row.calculated_value) if row.calculated_value else 0.0,
                'engine': row.calculation_engine,
                'is_circular': row.is_circular,
                'data_type': row.data_type,
                'mismatch_diff': float(row.mismatch_diff) if row.mismatch_diff else None,
                'converted_formula': row.converted_formula
            }
            
            # Categorize the issue
            formula = cell_info['formula'] or ''
            formula_upper = formula.upper()
            
            # Check for custom functions
            custom_funcs = ['IRR', 'XIRR', 'XNPV', 'MIRR']
            has_custom = any(f'{func}(' in formula_upper for func in custom_funcs)
            
            if has_custom:
                categories['custom_functions'].append(cell_info)
            elif cell_info['is_circular']:
                categories['circular'].append(cell_info)
            elif not formula or formula.strip() == '=' or formula.strip() == '=""':
                categories['empty_formulas'].append(cell_info)
            elif cell_info['engine'] == 'hyperformula' and cell_info['raw_value'] != 0:
                # HyperFormula evaluated to 0 but raw_value is different
                categories['hyperformula_errors'].append(cell_info)
            elif abs(cell_info['raw_value'] or 0) < 0.001:
                # Raw value is also near zero - might be legitimate
                categories['legitimate_zeros'].append(cell_info)
            else:
                categories['other'].append(cell_info)
        
        # Print results by category
        print_category(categories['custom_functions'], "CUSTOM FUNCTIONS (Need Implementation)")
        print_category(categories['circular'], "CIRCULAR REFERENCES")
        print_category(categories['empty_formulas'], "EMPTY/TRIVIAL FORMULAS")
        print_category(categories['hyperformula_errors'], "HYPERFORMULA EVALUATION ERRORS")
        print_category(categories['legitimate_zeros'], "LEGITIMATE ZEROS")
        print_category(categories['other'], "OTHER ISSUES")
        
        # Summary
        print("\n" + "=" * 100)
        print("SUMMARY:")
        print(f"  Total cells with issue: {len(results)}")
        print(f"  Custom functions: {len(categories['custom_functions'])}")
        print(f"  Circular references: {len(categories['circular'])}")
        print(f"  Empty formulas: {len(categories['empty_formulas'])}")
        print(f"  HyperFormula errors: {len(categories['hyperformula_errors'])}")
        print(f"  Legitimate zeros: {len(categories['legitimate_zeros'])}")
        print(f"  Other: {len(categories['other'])}")
        
        print("\n" + "=" * 100)
        print("RECOMMENDATIONS:")
        print()
        
        if categories['custom_functions']:
            print("1. CUSTOM FUNCTIONS:")
            print("   - These cells use IRR/XIRR/XNPV/MIRR which aren't supported yet")
            print("   - Should be marked with calculation_engine='custom'")
            print("   - Should have calculated_value=NULL (not 0)")
            print("   - ACTION: Set calculated_value to NULL for these cells")
            print()
        
        if categories['hyperformula_errors']:
            print("2. HYPERFORMULA ERRORS:")
            print("   - These formulas evaluated to 0 but raw_value suggests otherwise")
            print("   - Could be formula evaluation bugs or Excel compatibility issues")
            print("   - ACTION: Review formulas and check HyperFormula compatibility")
            print()
        
        if categories['circular']:
            print("3. CIRCULAR REFERENCES:")
            print("   - These cells are part of circular reference chains")
            print("   - Should have converged to correct value, not 0")
            print("   - ACTION: Check circular reference solver convergence")
            print()
        
        if categories['empty_formulas']:
            print("4. EMPTY FORMULAS:")
            print("   - These have trivial formulas like '=' or '=\"\"'")
            print("   - Legitimately evaluate to 0 or empty string")
            print("   - ACTION: Verify these are expected")
            print()
        
    finally:
        session.close()


def print_category(cells: List[Dict], title: str):
    """Print cells in a category."""
    if not cells:
        return
    
    print(f"\n{title} ({len(cells)} cells)")
    print("-" * 100)
    
    for cell in cells[:10]:  # Show first 10 of each category
        print(f"\nCell: {cell['sheet']}!{cell['cell']}")
        print(f"  Type: {cell['cell_type']}")
        print(f"  Formula: {cell['formula'][:80] if cell['formula'] else 'None'}")
        print(f"  Raw Value: {cell['raw_value']}")
        print(f"  Calculated Value: {cell['calculated_value']}")
        print(f"  Mismatch Diff: {cell['mismatch_diff']}")
        print(f"  Engine: {cell['engine']}")
        print(f"  Circular: {cell['is_circular']}")
    
    if len(cells) > 10:
        print(f"\n  ... and {len(cells) - 10} more cells")


def fix_zero_calculated_values(model_id: int = 1, dry_run: bool = True):
    """
    Fix cells that should have NULL instead of 0 for calculated_value.
    
    Args:
        model_id: Model ID to fix
        dry_run: If True, only show what would be fixed without making changes
    """
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Query cells that need fixing
        query = text("""
            SELECT 
                model_id, sheet_name, row_num, col_letter,
                cell, formula, calculation_engine, raw_value
            FROM cell
            WHERE model_id = :model_id
                AND has_mismatch = true
                AND calculated_value = 0
                AND (
                    calculation_engine = 'custom'
                    OR formula LIKE '%IRR(%'
                    OR formula LIKE '%XIRR(%'
                    OR formula LIKE '%XNPV(%'
                    OR formula LIKE '%MIRR(%'
                )
        """)
        
        results = session.execute(query, {'model_id': model_id}).fetchall()
        
        print(f"Found {len(results)} cells that should have NULL instead of 0")
        
        if dry_run:
            print("\nDRY RUN - No changes will be made")
            print("-" * 100)
            for row in results:
                print(f"  {row.sheet_name}!{row.cell}: {row.formula[:60]}")
        else:
            # Update cells
            update_query = text("""
                UPDATE cell
                SET 
                    calculated_value = NULL,
                    calculation_engine = 'custom',
                    updated_at = CURRENT_TIMESTAMP
                WHERE model_id = :model_id
                    AND has_mismatch = true
                    AND calculated_value = 0
                    AND (
                        calculation_engine = 'custom'
                        OR formula LIKE '%IRR(%'
                        OR formula LIKE '%XIRR(%'
                        OR formula LIKE '%XNPV(%'
                        OR formula LIKE '%MIRR(%'
                    )
            """)
            
            result = session.execute(update_query, {'model_id': model_id})
            session.commit()
            
            print(f"\nUpdated {result.rowcount} cells")
            print("  - Set calculated_value to NULL")
            print("  - Set calculation_engine to 'custom'")
    
    finally:
        session.close()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Diagnose and fix cells with zero calculated values'
    )
    parser.add_argument(
        '--model-id',
        type=int,
        default=1,
        help='Model ID to examine (default: 1)'
    )
    parser.add_argument(
        '--fix',
        action='store_true',
        help='Fix cells by setting calculated_value to NULL for custom functions'
    )
    parser.add_argument(
        '--no-dry-run',
        action='store_true',
        help='Actually apply fixes (use with --fix)'
    )
    
    args = parser.parse_args()
    
    if args.fix:
        fix_zero_calculated_values(
            model_id=args.model_id,
            dry_run=not args.no_dry_run
        )
    else:
        diagnose_zero_calculated_values(model_id=args.model_id)


if __name__ == '__main__':
    main()