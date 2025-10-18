#!/usr/bin/env python3
"""
Debug what's being sent to HyperFormula for a specific formula.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from services.excel_import_service import ExcelImportService

load_dotenv()


def debug_formula_context(model_id: int = 5, target_cell: str = "F7"):
    """Debug what context is being sent to HyperFormula for a specific cell."""
    
    engine = create_engine(os.getenv('DATABASE_URL'))
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Load all cells
        query = text("""
            SELECT 
                sheet_name, cell, row_num, col_letter, cell_type,
                raw_value, raw_text, formula, data_type, depends_on,
                is_circular, calculated_value
            FROM cell
            WHERE model_id = :model_id
            ORDER BY sheet_name, row_num, col_letter
        """)
        
        all_cells = session.execute(query, {'model_id': model_id}).fetchall()
        
        # Convert to cell data format
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
        
        # Initialize service
        service = ExcelImportService(session)
        
        # Build HyperFormula sheets
        print(f"Building HyperFormula context for {len(cells_data)} cells...\n")
        sheets_data = service._build_hyperformula_sheets(cells_data)
        
        # Find dependencies of target cell
        target_cell_data = next((c for c in cells_data if c['cell'] == target_cell), None)
        
        if not target_cell_data:
            print(f"Cell {target_cell} not found!")
            return
        
        print(f"Target Cell: {target_cell}")
        print(f"  Formula: {target_cell_data.get('formula')}")
        print(f"  Dependencies: {target_cell_data.get('depends_on')}")
        print(f"  Calculated value in DB: {target_cell_data.get('calculated_value', 'N/A')}")
        print()
        
        # Show what's in HyperFormula context for dependencies
        deps = target_cell_data.get('depends_on', [])
        print(f"Checking {len(deps)} dependencies in HyperFormula context:")
        print("-" * 80)
        
        for sheet in sheets_data:
            for cell in sheet['cells']:
                # Convert coordinates back to cell ref
                from services.formula_service import FormulaParser
                parser = FormulaParser()
                cell_addr = parser.coordinates_to_cell(cell['row'], cell['col'])
                cell_ref = f"{sheet['name']}!{cell_addr}"
                
                # Check if this is a dependency
                if cell_ref in deps or cell_addr in [d.split('!')[-1] for d in deps]:
                    print(f"\n  {cell_ref}:")
                    if 'formula' in cell:
                        print(f"    Type: formula")
                        print(f"    Value: {cell['formula']}")
                    elif 'value' in cell:
                        print(f"    Type: value")
                        print(f"    Value: {cell['value']}")
                        print(f"    Value type: {type(cell['value']).__name__}")
        
        # Check for text cells mentioned in formula
        formula = target_cell_data.get('formula', '')
        print(f"\n\nText values referenced in formula:")
        print("-" * 80)
        
        # Extract cell refs from formula
        import re
        cell_refs = re.findall(r'\$?[A-Z]+\$?\d+', formula)
        
        for ref in set(cell_refs):
            # Find this cell in database
            ref_clean = ref.replace('$', '')
            cell_in_db = next((c for c in cells_data if c['cell'] == ref_clean), None)
            
            if cell_in_db and cell_in_db.get('raw_text'):
                print(f"\n  {ref_clean}:")
                print(f"    In DB: raw_text = \"{cell_in_db['raw_text']}\"")
                
                # Check if in HyperFormula
                in_hf = False
                for sheet in sheets_data:
                    for hf_cell in sheet['cells']:
                        parser = FormulaParser()
                        cell_addr = parser.coordinates_to_cell(hf_cell['row'], hf_cell['col'])
                        if cell_addr == ref_clean:
                            in_hf = True
                            if 'value' in hf_cell:
                                print(f"    In HyperFormula: value = {hf_cell['value']} (type: {type(hf_cell['value']).__name__})")
                            else:
                                print(f"    In HyperFormula: formula = {hf_cell.get('formula')}")
                            break
                
                if not in_hf:
                    print(f"    ⚠️  NOT IN HYPERFORMULA CONTEXT!")
    
    finally:
        session.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-id', type=int, default=5)
    parser.add_argument('--cell', type=str, default='F7')
    
    args = parser.parse_args()
    
    debug_formula_context(args.model_id, args.cell)