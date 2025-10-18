#!/usr/bin/env python3
"""
Test if text values are being included in HyperFormula evaluation.
"""

import json
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_text_value_in_formula():
    """Test if HyperFormula can evaluate formulas with text value dependencies."""
    
    # Simulate the actual data structure
    request = {
        'sheets': [
            {
                'name': 'Sheet1',
                'cells': [
                    # Text value cells
                    {'row': 21, 'col': 1, 'value': 'On'},        # B22
                    {'row': 27, 'col': 1, 'value': 'Purchase'},  # B28
                    {'row': 22, 'col': 1, 'value': 0.7},         # B23
                    {'row': 5, 'col': 5, 'value': 175000000},    # F6
                    # Formula that depends on text
                    {'row': 6, 'col': 5, 'formula': '=IF(B22="On", B23 * F6, 0)'}  # F7
                ]
            }
        ],
        'queries': [
            {'sheet': 'Sheet1', 'row': 6, 'col': 5, 'cell': 'F7'}
        ]
    }
    
    print("Testing text value in formula evaluation:")
    print(json.dumps(request, indent=2))
    print("\n" + "="*80 + "\n")
    
    # Call HyperFormula
    process = subprocess.Popen(
        ['node', 'scripts/hyperformula_wrapper.js'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = process.communicate(json.dumps(request), timeout=10)
    
    print("STDOUT:")
    print(stdout)
    if stderr:
        print("\nSTDERR:")
        print(stderr)
    print("\nReturn code:", process.returncode)
    
    if process.returncode == 0:
        result = json.loads(stdout)
        print("\nParsed result:")
        print(json.dumps(result, indent=2))
        
        if result.get('success'):
            for res in result.get('results', []):
                print(f"\n{res['cell']}: {res['value']} (type: {res['type']})")
                expected = 0.7 * 175000000  # B23 * F6
                if res['type'] == 'number':
                    actual = res['value']
                    print(f"  Expected: {expected}")
                    print(f"  Actual: {actual}")
                    print(f"  Match: {'✓' if abs(actual - expected) < 1 else '✗'}")
                else:
                    print(f"  ERROR: Got type '{res['type']}' instead of 'number'")


if __name__ == '__main__':
    test_text_value_in_formula()