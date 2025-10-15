#!/usr/bin/env python3
"""
Audit script to ensure NO raw_value copying to calculated_value.

This script scans the codebase and database to verify that calculated_value
is NEVER copied from raw_value. This is a critical integrity check.

Usage:
    python data_repair/validate_no_copying.py
    pytest data_repair/validate_no_copying.py  # Run as test
"""

import sys
import os
from pathlib import Path
import re

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from dotenv import load_dotenv
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from backend.models.schema import Cell

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost/dcmodel')


def search_codebase_for_copying():
    """Search Python files for suspicious patterns."""
    
    suspicious_patterns = [
        r'calculated_value\s*=\s*raw_value',
        r'calculated_text\s*=\s*str\(raw_value\)',
        r'cell\.calculated_value\s*=\s*cell\.raw_value',
        r'calculated_value\s*=\s*cell\.raw_value',
        r'\.calculated_value\s*=\s*.*\.raw_value',
    ]
    
    violations = []
    project_root = Path(__file__).parent.parent
    
    for py_file in project_root.rglob('*.py'):
        # Skip this file itself
        if py_file.name == 'validate_no_copying.py':
            continue
        
        try:
            content = py_file.read_text()
            
            for i, line in enumerate(content.split('\n'), 1):
                for pattern in suspicious_patterns:
                    if re.search(pattern, line):
                        # Check if it's in a comment
                        if '#' in line and line.index('#') < line.index('='):
                            continue
                        
                        violations.append({
                            'file': str(py_file.relative_to(project_root)),
                            'line': i,
                            'content': line.strip(),
                            'pattern': pattern
                        })
        except Exception:
            pass  # Skip files that can't be read
    
    return violations


def check_database_suspicious_equality():
    """Check database for suspiciously high equality between raw and calculated."""
    
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Count formula cells where calculated_value == raw_value
        matching = session.query(func.count(Cell.cell)).filter(
            Cell.formula.isnot(None),
            Cell.calculated_value.isnot(None),
            Cell.raw_value.isnot(None),
            Cell.calculated_value == Cell.raw_value
        ).scalar()
        
        total_formulas = session.query(func.count(Cell.cell)).filter(
            Cell.formula.isnot(None),
            Cell.calculated_value.isnot(None)
        ).scalar()
        
        session.close()
        
        if total_formulas == 0:
            return {'suspicious': False, 'ratio': 0, 'matching': 0, 'total': 0}
        
        ratio = matching / total_formulas
        
        # Flag as suspicious if >90% match (could indicate copying)
        return {
            'suspicious': ratio > 0.90,
            'ratio': ratio,
            'matching': matching,
            'total': total_formulas
        }
        
    except Exception as e:
        return {'error': str(e)}


@click.command()
@click.option('--verbose', '-v', is_flag=True, help='Show detailed violations')
def validate(verbose: bool):
    """Validate that no raw_value copying occurs."""
    
    click.echo("\nValidating No Raw Value Copying")
    click.echo("=" * 60)
    
    # Check codebase
    click.echo("\n1. Scanning codebase for suspicious patterns...")
    violations = search_codebase_for_copying()
    
    if violations:
        click.echo(f"   ✗ Found {len(violations)} potential violations!")
        
        if verbose:
            click.echo("\n   Violations:")
            for v in violations:
                click.echo(f"     {v['file']}:{v['line']}")
                click.echo(f"       {v['content']}")
        else:
            click.echo("   Use --verbose to see details")
    else:
        click.echo("   ✓ No suspicious patterns found")
    
    # Check database
    click.echo("\n2. Checking database for suspicious equality...")
    
    try:
        db_check = check_database_suspicious_equality()
        
        if 'error' in db_check:
            click.echo(f"   ⚠ Database check failed: {db_check['error']}")
            click.echo("   (This is expected if database is not yet set up)")
        elif db_check['total'] == 0:
            click.echo("   ⚠ No formula cells with calculated values in database")
        else:
            ratio_pct = db_check['ratio'] * 100
            click.echo(f"   Formula cells: {db_check['total']}")
            click.echo(f"   Matching raw_value: {db_check['matching']} ({ratio_pct:.1f}%)")
            
            if db_check['suspicious']:
                click.echo(f"   ✗ SUSPICIOUS: {ratio_pct:.1f}% of formulas match raw_value")
                click.echo("   This may indicate raw_value copying!")
            else:
                click.echo(f"   ✓ Ratio is acceptable (<90%)")
    
    except Exception as e:
        click.echo(f"   ⚠ Database check error: {e}")
    
    click.echo("\n" + "=" * 60)
    
    if violations:
        click.echo("\n✗ VALIDATION FAILED - Code violations found")
        sys.exit(1)
    else:
        click.echo("\n✓ VALIDATION PASSED - No copying detected")


def test_no_raw_value_copying():
    """Pytest test version of validation."""
    violations = search_codebase_for_copying()
    
    assert len(violations) == 0, (
        f"Found {len(violations)} potential raw_value copying violations:\n" +
        "\n".join(f"  {v['file']}:{v['line']}: {v['content']}" for v in violations[:5])
    )


if __name__ == '__main__':
    validate()