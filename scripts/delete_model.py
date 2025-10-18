#!/usr/bin/env python3
"""
Delete a model and all its associated cells from the database.

This script deletes a model by ID, including all related cells (cascade delete).
Useful for testing or removing corrupted imports.
"""

import os
import sys

# Add parent directory to path
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


def delete_model(model_id: int, confirm: bool = False):
    """
    Delete a model and all its cells.
    
    Args:
        model_id: Model ID to delete
        confirm: If True, skip confirmation prompt
    """
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Get model info
        model_query = text("""
            SELECT id, name, original_filename, uploaded_at
            FROM models
            WHERE id = :model_id
        """)
        
        model = session.execute(model_query, {'model_id': model_id}).fetchone()
        
        if not model:
            logger.error(f"Model {model_id} not found")
            return
        
        # Get cell count
        cell_count_query = text("""
            SELECT COUNT(*) as count
            FROM cell
            WHERE model_id = :model_id
        """)
        
        cell_count = session.execute(cell_count_query, {'model_id': model_id}).fetchone().count
        
        # Display info
        logger.info("Model to be deleted:")
        logger.info(f"  ID: {model.id}")
        logger.info(f"  Name: {model.name}")
        logger.info(f"  Filename: {model.original_filename}")
        logger.info(f"  Uploaded: {model.uploaded_at}")
        logger.info(f"  Cells: {cell_count}")
        
        # Confirm deletion
        if not confirm:
            response = input("\nAre you sure you want to delete this model? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                logger.info("Deletion cancelled")
                return
        
        # Delete model (cascade will delete cells automatically)
        logger.info(f"Deleting model {model_id}...")
        
        delete_query = text("""
            DELETE FROM models
            WHERE id = :model_id
        """)
        
        session.execute(delete_query, {'model_id': model_id})
        session.commit()
        
        logger.info(f"✓ Successfully deleted model {model_id} and {cell_count} cells")
        
    except Exception as e:
        logger.error(f"Error deleting model: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def list_models():
    """List all models in the database."""
    engine = create_engine(get_database_url())
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        query = text("""
            SELECT 
                m.id,
                m.name,
                m.original_filename,
                m.uploaded_at,
                COUNT(c.model_id) as cell_count
            FROM models m
            LEFT JOIN cell c ON m.id = c.model_id
            GROUP BY m.id, m.name, m.original_filename, m.uploaded_at
            ORDER BY m.id
        """)
        
        models = session.execute(query).fetchall()
        
        if not models:
            logger.info("No models found in database")
            return
        
        logger.info(f"Found {len(models)} model(s):")
        logger.info("-" * 100)
        
        for model in models:
            logger.info(f"ID: {model.id:3d} | Name: {model.name:30s} | "
                       f"File: {model.original_filename:30s} | "
                       f"Cells: {model.cell_count:6d} | "
                       f"Uploaded: {model.uploaded_at}")
        
    finally:
        session.close()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Delete a model from the database',
        epilog='Example: python delete_model.py --model-id 1'
    )
    parser.add_argument(
        '--model-id',
        type=int,
        help='Model ID to delete'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List all models'
    )
    parser.add_argument(
        '--yes',
        action='store_true',
        help='Skip confirmation prompt'
    )
    
    args = parser.parse_args()
    
    if args.list:
        list_models()
    elif args.model_id:
        delete_model(args.model_id, confirm=args.yes)
    else:
        parser.print_help()
        print("\nTip: Use --list to see all models first")


if __name__ == '__main__':
    main()