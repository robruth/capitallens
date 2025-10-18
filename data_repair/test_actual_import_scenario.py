#!/usr/bin/env python3
"""
Test the exact scenario from the import with real data from model 5.
"""

import json
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from services.excel_import_service import ExcelImportService
from services.formula_service import FormulaParser

load_dotenv()


def test_real_scenario():
    """Test with actual data from model 5."""
    
    engine = create_engine(os.getenv('DATABASE_URL'))
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Load cells for F7 and its dependencies
        query = text("""
            SELECT 
                sheet_name, cell, row_num, col_letter, cell_type,
                raw_value, raw_text, formula, is_circular
            FROM cell
            WHERE model_id = 5
            AND cell IN ('F7', 'B22', 'B23', 'F6', 'B12', 'B14')
            ORDER BY cell
        """)
        
        cells = session.execute(query, {'model_id': 5}).fetchall()
        
        # Convert to cell_data format
        cells_data = []
        for row in cells:
            cell_data = {
                'sheet_name': row.sheet_name,
                'cell': row.cell,
                'cell_type': row.cell_type,
                'raw_value': float(row.raw_value) if row.raw_value else None,
                'raw_text': row.raw_text,
                'formula': row.formula,
                'is_circular': row.is_circular
            }
            cells_data.append(cell_data)
        
        print("Cells loaded from database:")
        for cell in cells_data:
            print(f"  {cell['cell']}: ", end='')
            if cell.get('formula'):
                print(f"formula={cell['formula'][:50]}")
            elif cell.get('raw_text'):
                print(f"text=\"{cell['raw_text']}\"")
            else:
                print(f"value={cell.get('raw_value')}")
        
        # Build HyperFormula sheets
        service = ExcelImportService(session)
        sheets_data = service._build_hyperformula_sheets(cells_data)
        
        print("\n\nHyperFormula sheets structure:")
        print(json.dumps(sheets_data, indent=2))
        
        # Try to evaluate F7
        parser = FormulaParser()
        row, col = parser.cell_to_coordinates('F7')
        
        print(f"\n\nEvaluating F7...")
        result = service.hf_evaluator.evaluate_batch(
            sheets_data=sheets_data,
            queries=[{
                'sheet': 'Sheet1',
                'row': row,
                'col': col,
                'cell': 'Sheet1!F7'
            }]
        )
        
        print(f"Result: {json.dumps(result, indent=2)}")
        
        if result.get('success') and result['results']:
            res = result['results'][0]
            print(f"\nF7 evaluation:")
            print(f"  Type: {res['type']}")
            print(f"  Value: {res['value']}")
            print(f"  Expected: 122499999.99999999")
    
    finally:
        session.close()


if __name__ == '__main__':
    test_real_scenario()