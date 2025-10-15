#!/usr/bin/env python3
"""
Excel to PostgreSQL Import CLI - Dual Mode

This script can operate in two modes:
1. Direct mode (default): Direct database import using services
2. API mode: Makes HTTP requests to FastAPI backend

Usage:
    # Direct mode (uses services directly)
    python scripts/excel_importer_cli.py import --file model.xlsx --name "Model Name"
    
    # API mode (uses FastAPI backend)
    python scripts/excel_importer_cli.py import --file model.xlsx --name "Model Name" --api-url http://localhost:8000
    
    # Validation
    python scripts/excel_importer_cli.py validate --model-id 1 [--api-url http://localhost:8000]
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import time
import logging
from typing import Optional

import click
from dotenv import load_dotenv
import requests
from websocket import create_connection, WebSocketException

# For direct mode
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.schema import Base
from services.excel_import_service import ExcelImportService
from services.validation_service import ValidationService

# Load environment variables
load_dotenv()

# Configure logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'cli.log')

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger('excel_importer_cli')

# Configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost/dcmodel')
DEFAULT_API_URL = os.getenv('API_URL', 'http://localhost:8000')


@click.group()
@click.option('--api-url', envvar='API_URL', help='FastAPI backend URL (enables API mode)')
@click.pass_context
def cli(ctx, api_url):
    """Excel to PostgreSQL Import CLI - Dual Mode Support"""
    ctx.ensure_object(dict)
    ctx.obj['api_url'] = api_url
    ctx.obj['mode'] = 'api' if api_url else 'direct'
    
    if api_url:
        click.echo(f"🌐 API Mode: Using backend at {api_url}")
    else:
        click.echo("💾 Direct Mode: Using local database")


@cli.command('import')
@click.option('--file', '-f', required=True, type=click.Path(exists=True),
              help='Path to Excel file to import')
@click.option('--name', '-n', required=True, help='Model name')
@click.option('--validate', is_flag=True, help='Run post-import validation')
@click.option('--api-url', envvar='API_URL', help='FastAPI backend URL (enables API mode)')
def import_cmd(file: str, name: str, validate: bool, api_url: Optional[str]):
    """Import an Excel workbook."""
    
    if api_url:
        click.echo(f"🌐 API Mode: Using backend at {api_url}")
        import_via_api(api_url, file, name, validate)
    else:
        click.echo("💾 Direct Mode: Using local database")
        import_direct(file, name, validate)


@cli.command('validate')
@click.option('--model-id', '-m', required=True, type=int,
              help='Model ID to validate')
@click.option('--api-url', envvar='API_URL', help='FastAPI backend URL (enables API mode)')
def validate_cmd(model_id: int, api_url: Optional[str]):
    """Validate an imported model."""
    
    if api_url:
        click.echo(f"🌐 API Mode: Using backend at {api_url}")
        validate_via_api(api_url, model_id)
    else:
        click.echo("💾 Direct Mode: Using local database")
        validate_direct(model_id)


# ============================================================================
# Direct Mode Implementation (Uses Services Directly)
# ============================================================================

def import_direct(file_path: str, model_name: str, validate_flag: bool):
    """Import file using direct database access."""
    click.echo(f"\n📁 Importing: {file_path}")
    click.echo(f"📝 Model name: {model_name}")
    
    try:
        # Create database engine and session
        engine = create_engine(DATABASE_URL)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Define progress callback
        def on_progress(stage: str, percent: float, message: str):
            # Show progress bar
            bar_length = 40
            filled = int(bar_length * percent / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            
            click.echo(f"\r[{bar}] {percent:.1f}% - {stage}: {message}", nl=False)
        
        # Import file using service
        click.echo("\n")
        service = ExcelImportService(session, progress_callback=on_progress)
        result = service.import_file(file_path, model_name, validate=validate_flag)
        
        click.echo()  # New line after progress bar
        
        # Check for errors
        if result.get('errors'):
            click.echo(f"\n⚠️  Errors encountered: {result['errors']}", err=True)
        
        if result.get('duplicate'):
            click.echo(f"\nℹ️  File already imported as Model ID: {result['model_id']}")
            return
        
        # Display results
        click.echo(f"\n✓ Import successful!")
        click.echo(f"Model ID: {result['model_id']}")
        click.echo(f"Model name: {model_name}")
        
        # Display statistics
        stats = result.get('stats', {})
        click.echo(f"\nStatistics:")
        click.echo(f"  Total cells: {stats.get('total_cells', 0)}")
        click.echo(f"  Formula cells: {stats.get('formula_cells', 0)}")
        click.echo(f"  Circular references: {stats.get('circular_references', 0)}")
        click.echo(f"  Exact matches: {stats.get('exact_matches', 0)}")
        click.echo(f"  Mismatches: {stats.get('mismatches', 0)}")
        
        # Display validation results if available
        if validate_flag and result.get('validation_results'):
            val_result = result['validation_results']
            click.echo(f"\nValidation:")
            click.echo(f"  Status: {val_result.get('status', 'unknown').upper()}")
            click.echo(f"  Matches: {val_result.get('matches', 0)}")
            click.echo(f"  Mismatches: {val_result.get('mismatches', 0)}")
        
        session.close()
        
    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        click.echo(f"\n✗ Import failed: {e}", err=True)
        sys.exit(1)


def validate_direct(model_id: int):
    """Validate model using direct database access."""
    click.echo(f"\n🔍 Validating Model #{model_id}...")
    
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Define progress callback
        def on_progress(stage: str, percent: float, message: str):
            bar_length = 40
            filled = int(bar_length * percent / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            click.echo(f"\r[{bar}] {percent:.1f}% - {message}", nl=False)
        
        service = ValidationService(session, progress_callback=on_progress)
        result = service.validate_model(model_id)
        
        click.echo()  # New line after progress
        
        click.echo(f"\nValidation Report for Model #{model_id}")
        click.echo("=" * 50)
        click.echo(f"Status: {result.get('status', 'unknown').upper()}")
        click.echo(f"Total formula cells: {result.get('total', 0)}")
        click.echo(f"Matches: {result.get('matches', 0)}")
        click.echo(f"Mismatches: {result.get('mismatches', 0)}")
        click.echo(f"Errors: {result.get('errors', 0)}")
        click.echo(f"NULL calculated: {result.get('null_calculated', 0)}")
        
        if result.get('mismatch_cells'):
            mismatch_list = result['mismatch_cells'][:10]
            click.echo(f"\nFirst 10 mismatches:")
            for mismatch in mismatch_list:
                click.echo(f"  {mismatch.get('cell_ref')}: diff={mismatch.get('diff')}")
            
            if len(result['mismatch_cells']) > 10:
                click.echo(f"  ... and {len(result['mismatch_cells']) - 10} more")
        
        session.close()
        
    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        click.echo(f"\n✗ Validation failed: {e}", err=True)
        sys.exit(1)


# ============================================================================
# API Mode Implementation (Uses FastAPI Backend)
# ============================================================================

def import_via_api(api_url: str, file_path: str, model_name: str, validate_flag: bool):
    """Import file via FastAPI backend."""
    
    click.echo(f"\n📤 Uploading {file_path} to {api_url}...")
    
    try:
        # Upload file
        with open(file_path, 'rb') as f:
            files = {
                'file': (Path(file_path).name, f, 
                        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            }
            data = {
                'model_name': model_name,
                'validate': str(validate_flag).lower()
            }
            
            response = requests.post(
                f"{api_url}/api/import/upload",
                files=files,
                data=data,
                timeout=30
            )
        
        if response.status_code != 202:
            click.echo(f"❌ Upload failed ({response.status_code}): {response.text}", err=True)
            sys.exit(1)
        
        result = response.json()
        job_id = result['job_id']
        
        click.echo(f"✓ Upload successful. Job ID: {job_id}")
        click.echo("🔄 Tracking progress via WebSocket...\n")
        
        # Try WebSocket first, fall back to polling if it fails
        try:
            track_progress_websocket(api_url, job_id, model_name)
        except (WebSocketException, ConnectionError, Exception) as e:
            logger.warning(f"WebSocket connection failed: {e}")
            click.echo(f"\n⚠️  WebSocket unavailable, falling back to polling...")
            track_progress_polling(api_url, job_id, model_name)
        
    except requests.exceptions.RequestException as e:
        click.echo(f"❌ Network error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        click.echo(f"❌ Upload failed: {e}", err=True)
        sys.exit(1)


def track_progress_websocket(api_url: str, job_id: str, model_name: str):
    """Track import progress via WebSocket."""
    
    ws_url = api_url.replace('http://', 'ws://').replace('https://', 'wss://')
    ws_url = f"{ws_url}/ws/import/{job_id}"
    
    ws = create_connection(ws_url, timeout=5)
    
    try:
        while True:
            message = ws.recv()
            data = json.loads(message)
            
            if 'error' in data:
                click.echo(f"\n❌ Error: {data['error']}", err=True)
                sys.exit(1)
            
            if 'progress' in data:
                progress = data['progress']
                stage = progress['stage']
                percent = progress['percent']
                message_text = progress['message']
                
                # Show progress bar
                bar_length = 40
                filled = int(bar_length * percent / 100)
                bar = '█' * filled + '░' * (bar_length - filled)
                
                click.echo(f"\r[{bar}] {percent:.1f}% - {stage}: {message_text}", nl=False)
            
            if data.get('status') in ['success', 'failed', 'cancelled']:
                click.echo()  # New line after progress bar
                
                if data['status'] == 'success':
                    result = data.get('result', {})
                    click.echo(f"\n✓ Import successful!")
                    click.echo(f"Model ID: {result.get('model_id')}")
                    click.echo(f"Model name: {model_name}")
                    
                    stats = result.get('stats', {})
                    if stats:
                        click.echo(f"\nStatistics:")
                        click.echo(f"  Total cells: {stats.get('total_cells', 0)}")
                        click.echo(f"  Formula cells: {stats.get('formula_cells', 0)}")
                        click.echo(f"  Circular references: {stats.get('circular_references', 0)}")
                        click.echo(f"  Exact matches: {stats.get('exact_matches', 0)}")
                        click.echo(f"  Mismatches: {stats.get('mismatches', 0)}")
                    
                    val_result = result.get('validation_results')
                    if val_result:
                        click.echo(f"\nValidation:")
                        click.echo(f"  Status: {val_result.get('status', 'unknown').upper()}")
                        click.echo(f"  Matches: {val_result.get('matches', 0)}")
                        click.echo(f"  Mismatches: {val_result.get('mismatches', 0)}")
                        
                elif data['status'] == 'failed':
                    error = data.get('error', {})
                    click.echo(f"\n❌ Import failed: {error.get('error', 'Unknown error')}", err=True)
                    if error.get('traceback'):
                        logger.error(f"Full traceback:\n{error['traceback']}")
                    sys.exit(1)
                else:
                    click.echo(f"\n⚠️  Import {data['status']}", err=True)
                    sys.exit(1)
                
                break
        
        ws.close()
        
    except Exception as e:
        ws.close()
        raise


def track_progress_polling(api_url: str, job_id: str, model_name: str):
    """Track import progress via REST API polling."""
    
    click.echo("⏱️  Polling for status updates...\n")
    
    last_percent = 0
    
    while True:
        try:
            response = requests.get(f"{api_url}/api/import/job/{job_id}", timeout=10)
            
            if response.status_code != 200:
                click.echo(f"\n❌ Error checking status: {response.text}", err=True)
                sys.exit(1)
            
            data = response.json()
            status = data['status']
            
            # Show progress if available
            progress = data.get('progress')
            if progress:
                percent = progress['percent']
                
                # Only update if progress changed
                if percent != last_percent:
                    stage = progress['stage']
                    message = progress['message']
                    
                    bar_length = 40
                    filled = int(bar_length * percent / 100)
                    bar = '█' * filled + '░' * (bar_length - filled)
                    
                    click.echo(f"\r[{bar}] {percent:.1f}% - {stage}: {message}", nl=False)
                    last_percent = percent
            
            # Check if job is complete
            if status in ['success', 'failed', 'cancelled']:
                click.echo()  # New line after progress bar
                
                if status == 'success':
                    result = data.get('result', {})
                    click.echo(f"\n✓ Import successful!")
                    click.echo(f"Model ID: {result.get('model_id')}")
                    click.echo(f"Model name: {model_name}")
                    
                    stats = result.get('stats', {})
                    if stats:
                        click.echo(f"\nStatistics:")
                        click.echo(f"  Total cells: {stats.get('total_cells', 0)}")
                        click.echo(f"  Formula cells: {stats.get('formula_cells', 0)}")
                        click.echo(f"  Circular references: {stats.get('circular_references', 0)}")
                else:
                    error = data.get('error', {})
                    click.echo(f"\n❌ Import {status}: {error.get('error', 'Unknown error')}", err=True)
                    sys.exit(1)
                
                break
            
            # Wait before next poll
            time.sleep(1)
            
        except requests.exceptions.RequestException as e:
            click.echo(f"\n❌ Network error: {e}", err=True)
            sys.exit(1)


def validate_via_api(api_url: str, model_id: int):
    """Validate model via FastAPI backend."""
    
    click.echo(f"\n🔍 Triggering validation for Model #{model_id}...")
    
    try:
        # Trigger validation job
        response = requests.post(
            f"{api_url}/api/models/{model_id}/validate",
            timeout=10
        )
        
        if response.status_code == 404:
            click.echo(f"❌ Model #{model_id} not found", err=True)
            sys.exit(1)
        elif response.status_code != 202:
            click.echo(f"❌ Validation failed ({response.status_code}): {response.text}", err=True)
            sys.exit(1)
        
        result = response.json()
        job_id = result['job_id']
        
        click.echo(f"✓ Validation job started. Job ID: {job_id}")
        click.echo("🔄 Tracking progress...\n")
        
        # Try WebSocket first
        try:
            ws_url = api_url.replace('http://', 'ws://').replace('https://', 'wss://')
            ws_url = f"{ws_url}/ws/validation/{job_id}"
            
            ws = create_connection(ws_url, timeout=5)
            
            while True:
                message = ws.recv()
                data = json.loads(message)
                
                if 'progress' in data:
                    progress = data['progress']
                    percent = progress['percent']
                    stage = progress['stage']
                    msg = progress['message']
                    
                    bar_length = 40
                    filled = int(bar_length * percent / 100)
                    bar = '█' * filled + '░' * (bar_length - filled)
                    
                    click.echo(f"\r[{bar}] {percent:.1f}% - {stage}: {msg}", nl=False)
                
                if data.get('status') in ['success', 'failed', 'cancelled']:
                    click.echo()
                    
                    if data['status'] == 'success':
                        val_result = data.get('result', {})
                        
                        click.echo(f"\nValidation Report for Model #{model_id}")
                        click.echo("=" * 50)
                        click.echo(f"Status: {val_result.get('status', 'unknown').upper()}")
                        click.echo(f"Total formula cells: {val_result.get('total', 0)}")
                        click.echo(f"Matches: {val_result.get('matches', 0)}")
                        click.echo(f"Mismatches: {val_result.get('mismatches', 0)}")
                        click.echo(f"Errors: {val_result.get('errors', 0)}")
                        click.echo(f"NULL calculated: {val_result.get('null_calculated', 0)}")
                    else:
                        error = data.get('error', {})
                        click.echo(f"\n❌ Validation failed: {error.get('error', 'Unknown error')}", err=True)
                        sys.exit(1)
                    
                    break
            
            ws.close()
            
        except (WebSocketException, ConnectionError) as e:
            logger.warning(f"WebSocket failed, falling back to polling: {e}")
            click.echo("\n⚠️  Falling back to status polling...")
            
            # Fall back to polling
            while True:
                response = requests.get(f"{api_url}/api/import/job/{job_id}")
                data = response.json()
                
                if data.get('progress'):
                    progress = data['progress']
                    click.echo(f"\r{progress['stage']}: {progress['message']} ({progress['percent']:.1f}%)", nl=False)
                
                if data['status'] in ['success', 'failed']:
                    click.echo()
                    
                    if data['status'] == 'success':
                        click.echo("\n✓ Validation complete")
                        val_result = data.get('result', {})
                        click.echo(f"Status: {val_result.get('status', 'unknown').upper()}")
                        click.echo(f"Matches: {val_result.get('matches', 0)}")
                        click.echo(f"Mismatches: {val_result.get('mismatches', 0)}")
                    else:
                        click.echo(f"\n❌ Validation failed", err=True)
                        sys.exit(1)
                    
                    break
                
                time.sleep(1)
        
    except requests.exceptions.RequestException as e:
        click.echo(f"❌ Network error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()