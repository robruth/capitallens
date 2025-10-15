"""
Pytest configuration and fixtures for Excel import tests.
"""

import os
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from backend.models.schema import Base

# Load environment
load_dotenv()

# Test database URL (use separate test database)
TEST_DATABASE_URL = os.getenv('TEST_DATABASE_URL', 
                               'postgresql://postgres:s3cr3t@localhost/dcmodel_test')


@pytest.fixture(scope='session')
def engine():
    """Create test database engine."""
    eng = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture(scope='function')
def session(engine):
    """Create a new database session for a test."""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    sess = Session()
    
    yield sess
    
    sess.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope='session')
def sample_files():
    """Provide paths to sample Excel files."""
    project_root = Path(__file__).parent.parent
    return {
        'dcmodel': project_root / 'dcmodel_template_hf_final_v32.xlsx',
        'gpuaas': project_root / 'gpuaas_calculator v33.xlsx'
    }


@pytest.fixture
def mock_circular_cells():
    """Mock circular reference data for testing."""
    return {
        'Sheet1!A1': {
            'formula': '=B1+1',
            'depends_on': ['Sheet1!B1'],
            'raw_value': 2.0
        },
        'Sheet1!B1': {
            'formula': '=A1/2',
            'depends_on': ['Sheet1!A1'],
            'raw_value': 1.0
        }
    }


@pytest.fixture
def mock_text_formula_cell():
    """Mock cell with text formula."""
    return {
        'sheet_name': 'Sheet1',
        'cell': 'A1',
        'formula': '=""',
        'cell_type': 'formula_text',
        'raw_value': None
    }