#!/usr/bin/env python3
"""
Fix NULL calculated values by re-evaluating formulas.

This script re-runs the full evaluation pipeline for cells with NULL
calculated_value or calculated_text, attempting to fix them.

Usage:
    python data_repair/fix_null_calculated_values.py --model-id 1
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import logging

from backend.models.schema import Model, Cell

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost/dcmodel')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('fix_nulls')


@click.command()
@click.option('--model-id', '-m', required=True, type=int, help='Model ID to fix')
@click.option('--dry-run', is_flag=True, help='Show what would be fixed without applying changes')
def fix_nulls(model_id: int, dry_run: bool):
    """Fix NULL calculated values in a model."""
    
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Get model
        model = session.query(Model).get(model_id)
        if not model:
            click.echo(f"Error: Model {model_id} not found", err=True)
            sys.exit(1)
        
        click.echo(f"\nFixing NULL Values")
        click.echo(f"{'=' * 60}")
        click.echo(f"Model: {model.name} (ID: {model.id})")
        click.echo(f"Mode: {'DRY RUN' if dry_run else 'APPLY CHANGES'}")
        click.echo(f"")
        
        # Query cells with NULL calculated values
        null_cells = session.query(Cell).filter(
            Cell.model_id == model_id,
            Cell.formula.isnot(None),
            Cell.calculated_value.is_(None),
            Cell.calculated_text.is_(None)
        ).all()
        
        click.echo(f"Found {len(null_cells)} cells with NULL calculated values")
        
        if not null_cells:
            click.echo("✓ No NULL values to fix!")
            session.close()
            return
        
        # Placeholder: Full re-evaluation would go here
        # For now, just show what would be done
        
        click.echo(f"")
        click.echo("Analysis:")
        click.echo("-" * 60)
        
        circular_count = sum(1 for c in null_cells if c.is_circular)
        non_circular_count = len(null_cells) - circular_count
        
        click.echo(f"  Circular references: {circular_count}")
        click.echo(f"  Non-circular: {non_circular_count}")
        click.echo(f"")
        
        if not dry_run:
            click.echo("WARNING: Full re-evaluation not yet implemented")
            click.echo("Would re-evaluate using:")
            click.echo("  1. HyperFormula for standard formulas")
            click.echo("  2. Iterative solver for circular references")
            click.echo("  3. Custom evaluators for complex functions")
            click.echo(f"")
            click.echo("CRITICAL: Would NEVER copy raw_value to calculated_value")
            click.echo("          Only store actual evaluation results or NULL")
        
        if dry_run:
            click.echo(f"")
            click.echo("Dry run complete - no changes made")
        else:
            click.echo(f"")
            click.echo("Fix operation pending full implementation")
        
        session.close()
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        logger.error(f"Fix failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    fix_nulls()