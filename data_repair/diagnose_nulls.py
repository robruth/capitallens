#!/usr/bin/env python3
"""
Diagnostic tool for analyzing NULL calculated values.

This script analyzes cells with NULL calculated_value/calculated_text to identify
root causes and suggest fixes.

Usage:
    python data_repair/diagnose_nulls.py --model-id 1
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from dotenv import load_dotenv
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from collections import defaultdict

from backend.models.schema import Model, Cell

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost/dcmodel')


@click.command()
@click.option('--model-id', '-m', required=True, type=int, help='Model ID to diagnose')
def diagnose(model_id: int):
    """Diagnose NULL calculated values in a model."""
    
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Get model
        model = session.query(Model).get(model_id)
        if not model:
            click.echo(f"Error: Model {model_id} not found", err=True)
            sys.exit(1)
        
        click.echo(f"\nNULL Value Diagnostic Report")
        click.echo(f"{'=' * 60}")
        click.echo(f"Model: {model.name} (ID: {model.id})")
        click.echo(f"File: {model.file_path}")
        click.echo(f"")
        
        # Query cells with NULL calculated values (formulas only)
        null_cells = session.query(Cell).filter(
            Cell.model_id == model_id,
            Cell.formula.isnot(None),
            Cell.calculated_value.is_(None),
            Cell.calculated_text.is_(None)
        ).all()
        
        total_formulas = session.query(func.count(Cell.cell)).filter(
            Cell.model_id == model_id,
            Cell.formula.isnot(None)
        ).scalar()
        
        click.echo(f"Total formula cells: {total_formulas}")
        click.echo(f"NULL calculated values: {len(null_cells)} ({len(null_cells)/total_formulas*100:.1f}%)")
        click.echo(f"")
        
        if not null_cells:
            click.echo("✓ No NULL values found!")
            session.close()
            return
        
        # Analyze by cause
        causes = defaultdict(list)
        
        for cell in null_cells:
            if cell.is_circular:
                causes['circular'].append(cell)
            elif cell.calculation_engine == 'hyperformula':
                causes['hyperformula_unsupported'].append(cell)
            elif cell.calculation_engine == 'custom':
                causes['custom_failed'].append(cell)
            else:
                causes['unknown'].append(cell)
        
        click.echo("Breakdown by cause:")
        click.echo("-" * 60)
        
        for cause, cells in sorted(causes.items(), key=lambda x: len(x[1]), reverse=True):
            pct = len(cells) / len(null_cells) * 100
            click.echo(f"  {cause}: {len(cells)} ({pct:.1f}%)")
        
        click.echo(f"")
        
        # Show examples
        click.echo("Sample NULL cells:")
        click.echo("-" * 60)
        
        for i, cell in enumerate(null_cells[:10]):
            formula_preview = cell.formula[:50] + "..." if len(cell.formula) > 50 else cell.formula
            cause_tag = ""
            if cell.is_circular:
                cause_tag = "[CIRCULAR]"
            elif cell.calculation_engine:
                cause_tag = f"[{cell.calculation_engine.upper()}]"
            
            click.echo(f"  {cell.sheet_name}!{cell.cell}: {formula_preview} {cause_tag}")
        
        if len(null_cells) > 10:
            click.echo(f"  ... and {len(null_cells) - 10} more")
        
        click.echo(f"")
        
        # Suggestions
        click.echo("Suggested fixes:")
        click.echo("-" * 60)
        
        if 'circular' in causes and len(causes['circular']) > 0:
            click.echo(f"  • {len(causes['circular'])} circular references detected")
            click.echo(f"    → Run iterative solver: python data_repair/fix_null_calculated_values.py --model-id {model_id}")
        
        if 'hyperformula_unsupported' in causes and len(causes['hyperformula_unsupported']) > 0:
            click.echo(f"  • {len(causes['hyperformula_unsupported'])} HyperFormula failures")
            click.echo(f"    → Check if HyperFormula is installed: npm list -g hyperformula")
            click.echo(f"    → Review unsupported functions")
        
        if 'custom_failed' in causes and len(causes['custom_failed']) > 0:
            click.echo(f"  • {len(causes['custom_failed'])} custom evaluation failures")
            click.echo(f"    → Review formula complexity and dependencies")
        
        click.echo(f"")
        
        # Sheet breakdown
        sheet_stats = defaultdict(int)
        for cell in null_cells:
            sheet_stats[cell.sheet_name] += 1
        
        if len(sheet_stats) > 1:
            click.echo("By sheet:")
            click.echo("-" * 60)
            for sheet, count in sorted(sheet_stats.items(), key=lambda x: x[1], reverse=True):
                click.echo(f"  {sheet}: {count}")
        
        session.close()
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    diagnose()