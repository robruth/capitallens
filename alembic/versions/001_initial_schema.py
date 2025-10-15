"""Initial schema for Excel import system

Revision ID: 001_initial_schema
Revises: 
Create Date: 2025-10-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create models table
    op.create_table(
        'models',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False, comment='User-friendly model name'),
        sa.Column('original_filename', sa.String(length=255), nullable=True, comment='Original Excel filename'),
        sa.Column('file_path', sa.String(length=512), nullable=True, comment='Path to stored Excel file (hash-based)'),
        sa.Column('file_hash', sa.String(length=64), nullable=False, comment='SHA256 hash for duplicate detection'),
        sa.Column('uploaded_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), 
                  nullable=False, comment='Initial upload timestamp'),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), 
                  nullable=False, comment='Last modification timestamp'),
        sa.Column('workbook_metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}',
                  nullable=False, comment='Workbook metadata: sheets, counts, dropdowns'),
        sa.Column('import_summary', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', 
                  nullable=False, comment='Import statistics: matches, mismatches, errors'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('file_hash'),
        comment='Represents an imported Excel workbook'
    )
    
    # Create indexes on models table
    op.create_index('idx_models_hash', 'models', ['file_hash'])
    op.create_index('idx_models_uploaded_at', 'models', ['uploaded_at'])
    
    # Create cell table
    op.create_table(
        'cell',
        sa.Column('model_id', sa.Integer(), nullable=False),
        sa.Column('sheet_name', sa.String(length=255), nullable=False, comment='Worksheet name'),
        sa.Column('row_num', sa.Integer(), nullable=False, comment='1-based row number'),
        sa.Column('col_letter', sa.String(length=10), nullable=False, comment='Column letter(s) e.g., A, B, AA'),
        sa.Column('cell', sa.String(length=10), nullable=False, comment='Cell address e.g., A1, B24'),
        sa.Column('cell_type', sa.String(length=20), nullable=True,
                  comment='Type: value (no formula), formula (numeric), formula_text (text)'),
        sa.Column('raw_value', sa.Numeric(precision=20, scale=10), nullable=True,
                  comment='Original numeric value from Excel'),
        sa.Column('raw_text', sa.Text(), nullable=True,
                  comment='Original text value from Excel (for text data types)'),
        sa.Column('formula', sa.Text(), nullable=True, comment='Formula text if cell contains formula'),
        sa.Column('data_type', sa.String(length=20), server_default='text', nullable=False, 
                  comment='Inferred data type'),
        sa.Column('depends_on', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', 
                  nullable=False, comment='Array of cell references this formula depends on'),
        sa.Column('is_circular', sa.Boolean(), server_default='false', nullable=False, 
                  comment='True if part of circular reference chain'),
        sa.Column('has_validation', sa.Boolean(), server_default='false', nullable=False, 
                  comment='True if cell has data validation'),
        sa.Column('validation_type', sa.String(length=50), nullable=True, 
                  comment='Validation type e.g., dropdown, list'),
        sa.Column('validation_options', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', 
                  nullable=False, comment='Array of allowed values for validation'),
        sa.Column('calculation_engine', sa.String(length=20), server_default='none', nullable=False, 
                  comment='Engine used for calculation'),
        sa.Column('converted_formula', sa.Text(), nullable=True, 
                  comment='Formula converted for evaluation engine'),
        sa.Column('calculated_value', sa.Numeric(precision=20, scale=10), nullable=True, 
                  comment='Calculated numeric result (NULL if unable to calculate)'),
        sa.Column('calculated_text', sa.Text(), nullable=True, 
                  comment='Calculated text result for formula_text type'),
        sa.Column('style', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', 
                  nullable=False, comment='Cell style: font, borders, colors'),
        sa.Column('has_mismatch', sa.Boolean(), server_default='false', nullable=False, 
                  comment='True if calculated value differs from raw_value'),
        sa.Column('mismatch_diff', sa.Numeric(precision=20, scale=10), nullable=True, 
                  comment='Absolute difference between calculated and raw values'),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), 
                  nullable=False, comment='Last update timestamp'),
        sa.CheckConstraint("cell_type IN ('value', 'formula', 'formula_text')", name='cell_cell_type_check'),
        sa.CheckConstraint("data_type IN ('number', 'text', 'date', 'boolean')", name='cell_data_type_check'),
        sa.CheckConstraint("calculation_engine IN ('none', 'hyperformula', 'custom')", 
                          name='cell_calculation_engine_check'),
        sa.ForeignKeyConstraint(['model_id'], ['models.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('model_id', 'sheet_name', 'row_num', 'col_letter'),
        comment='Represents a single cell from an Excel worksheet'
    )
    
    # Create indexes on cell table
    op.create_index('idx_cell_model_sheet', 'cell', ['model_id', 'sheet_name'])
    op.create_index('idx_cell_depends_gin', 'cell', ['depends_on'], postgresql_using='gin')
    op.create_index('idx_cell_engine', 'cell', ['calculation_engine'])
    op.create_index('idx_cell_circular', 'cell', ['is_circular'], 
                    postgresql_where='is_circular = true')
    op.create_index('idx_cell_mismatch', 'cell', ['has_mismatch'], 
                    postgresql_where='has_mismatch = true')
    op.create_index('idx_cell_formula', 'cell', ['model_id'], 
                    postgresql_where='formula IS NOT NULL')
    op.create_index('idx_cell_null_calculated', 'cell', ['model_id'], 
                    postgresql_where='calculated_value IS NULL AND formula IS NOT NULL')


def downgrade() -> None:
    # Drop cell table and indexes
    op.drop_index('idx_cell_null_calculated', table_name='cell')
    op.drop_index('idx_cell_formula', table_name='cell')
    op.drop_index('idx_cell_mismatch', table_name='cell')
    op.drop_index('idx_cell_circular', table_name='cell')
    op.drop_index('idx_cell_engine', table_name='cell')
    op.drop_index('idx_cell_depends_gin', table_name='cell')
    op.drop_index('idx_cell_model_sheet', table_name='cell')
    op.drop_table('cell')
    
    # Drop models table and indexes
    op.drop_index('idx_models_uploaded_at', table_name='models')
    op.drop_index('idx_models_hash', table_name='models')
    op.drop_table('models')