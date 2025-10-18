#!/usr/bin/env python3
"""
Test HyperFormula with a simple circular reference example.
"""

import json
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_simple_circular():
    """Test HyperFormula with a simple circular reference: A1=B1+1, B1=A1+1"""
    
    # Simple circular reference
    request = {
        'sheets': [
            {
                'name': 'Sheet1',
                'cells': [
                    {'row': 0, 'col': 0, 'formula': '=B1+1'},  # A1 = B1+1
                    {'row': 0, 'col': 1, 'formula': '=A1+1'}   # B1 = A1+1
                ]
            }
        ],
        'queries': [
            {'sheet': 'Sheet1', 'row': 0, 'col': 0, 'cell': 'A1'},
            {'sheet': 'Sheet1', 'row': 0, 'col': 1, 'cell': 'B1'}
        ]
    }
    
    print("Testing simple circular reference:")
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
    print("\nSTDERR:")
    print(stderr)
    print("\nReturn code:", process.returncode)
    
    if process.returncode == 0:
        result = json.loads(stdout)
        print("\nParsed result:")
        print(json.dumps(result, indent=2))
        
        for res in result.get('results', []):
            print(f"\n{res['cell']}: {res['value']} (type: {res['type']})")


if __name__ == '__main__':
    test_simple_circular()