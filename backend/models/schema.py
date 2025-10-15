"""
SQLAlchemy models for the Excel import system.

This module defines the database schema using SQLAlchemy ORM,
matching the schema defined in Alembic migrations.
"""

from datetime import datetime
from sqlalchemy import (
    Boolean, Column, Integer, String, Text, Numeric, TIMESTAMP,
    ForeignKey, CheckConstraint, Index, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Model(Base):
    """Represents an imported Excel workbook."""
    
    __tablename__ = 'models'
    __table_args__ = (
        Index('idx_models_hash', 'file_hash'),
        Index('idx_models_uploaded_at', 'uploaded_at'),
        {'comment': 'Represents an imported Excel workbook'}
    )
    
    id = Column(
        Integer, 
        primary_key=True, 
        autoincrement=True,
        nullable=False
    )
    name = Column(
        String(255), 
        nullable=False,
        comment='User-friendly model name'
    )
    original_filename = Column(
        String(255), 
        nullable=True,
        comment='Original Excel filename'
    )
    file_path = Column(
        String(512), 
        nullable=True,
        comment='Path to stored Excel file (hash-based)'
    )
    file_hash = Column(
        String(64), 
        nullable=False, 
        unique=True,
        comment='SHA256 hash for duplicate detection'
    )
    uploaded_at = Column(
        TIMESTAMP, 
        server_default=text('CURRENT_TIMESTAMP'),
        nullable=False,
        comment='Initial upload timestamp'
    )
    updated_at = Column(
        TIMESTAMP, 
        server_default=text('CURRENT_TIMESTAMP'),
        nullable=False,
        comment='Last modification timestamp'
    )
    workbook_metadata = Column(
        JSONB, 
        server_default='{}',
        nullable=False,
        comment='Workbook metadata: sheets, counts, dropdowns'
    )
    import_summary = Column(
        JSONB, 
        server_default='{}',
        nullable=False,
        comment='Import statistics: matches, mismatches, errors'
    )
    
    # Relationships
    cells = relationship('Cell', back_populates='model', cascade='all, delete-orphan')
    jobs = relationship('JobRun', back_populates='model')
    
    def __repr__(self):
        return f"<Model(id={self.id}, name='{self.name}', file_hash='{self.file_hash[:8]}...')>"


class Cell(Base):
    """Represents a single cell from an Excel worksheet."""
    
    __tablename__ = 'cell'
    __table_args__ = (
        CheckConstraint(
            "cell_type IN ('value', 'formula', 'formula_text')", 
            name='cell_cell_type_check'
        ),
        CheckConstraint(
            "data_type IN ('number', 'text', 'date', 'boolean')", 
            name='cell_data_type_check'
        ),
        CheckConstraint(
            "calculation_engine IN ('none', 'hyperformula', 'custom')", 
            name='cell_calculation_engine_check'
        ),
        Index('idx_cell_model_sheet', 'model_id', 'sheet_name'),
        Index('idx_cell_depends_gin', 'depends_on', postgresql_using='gin'),
        Index('idx_cell_engine', 'calculation_engine'),
        Index('idx_cell_circular', 'is_circular', postgresql_where=text('is_circular = true')),
        Index('idx_cell_mismatch', 'has_mismatch', postgresql_where=text('has_mismatch = true')),
        Index('idx_cell_formula', 'model_id', postgresql_where=text('formula IS NOT NULL')),
        Index('idx_cell_null_calculated', 'model_id', 
              postgresql_where=text('calculated_value IS NULL AND formula IS NOT NULL')),
        {'comment': 'Represents a single cell from an Excel worksheet'}
    )
    
    model_id = Column(
        Integer, 
        ForeignKey('models.id', ondelete='CASCADE'),
        primary_key=True,
        nullable=False
    )
    sheet_name = Column(
        String(255), 
        primary_key=True,
        nullable=False,
        comment='Worksheet name'
    )
    row_num = Column(
        Integer, 
        primary_key=True,
        nullable=False,
        comment='1-based row number'
    )
    col_letter = Column(
        String(10), 
        primary_key=True,
        nullable=False,
        comment='Column letter(s) e.g., A, B, AA'
    )
    cell = Column(
        String(10), 
        nullable=False,
        comment='Cell address e.g., A1, B24'
    )
    cell_type = Column(
        String(20), 
        nullable=True,
        comment='Type: value (no formula), formula (numeric), formula_text (text)'
    )
    raw_value = Column(
        Numeric(precision=20, scale=10), 
        nullable=True,
        comment='Original numeric value from Excel'
    )
    raw_text = Column(
        Text, 
        nullable=True,
        comment='Original text value from Excel (for text data types)'
    )
    formula = Column(
        Text, 
        nullable=True,
        comment='Formula text if cell contains formula'
    )
    data_type = Column(
        String(20), 
        server_default='text',
        nullable=False,
        comment='Inferred data type'
    )
    depends_on = Column(
        JSONB, 
        server_default='[]',
        nullable=False,
        comment='Array of cell references this formula depends on'
    )
    is_circular = Column(
        Boolean, 
        server_default='false',
        nullable=False,
        comment='True if part of circular reference chain'
    )
    has_validation = Column(
        Boolean, 
        server_default='false',
        nullable=False,
        comment='True if cell has data validation'
    )
    validation_type = Column(
        String(50), 
        nullable=True,
        comment='Validation type e.g., dropdown, list'
    )
    validation_options = Column(
        JSONB, 
        server_default='[]',
        nullable=False,
        comment='Array of allowed values for validation'
    )
    calculation_engine = Column(
        String(20), 
        server_default='none',
        nullable=False,
        comment='Engine used for calculation'
    )
    converted_formula = Column(
        Text, 
        nullable=True,
        comment='Formula converted for evaluation engine'
    )
    calculated_value = Column(
        Numeric(precision=20, scale=10), 
        nullable=True,
        comment='Calculated numeric result (NULL if unable to calculate)'
    )
    calculated_text = Column(
        Text, 
        nullable=True,
        comment='Calculated text result for formula_text type'
    )
    style = Column(
        JSONB, 
        server_default='{}',
        nullable=False,
        comment='Cell style: font, borders, colors'
    )
    has_mismatch = Column(
        Boolean, 
        server_default='false',
        nullable=False,
        comment='True if calculated value differs from raw_value'
    )
    mismatch_diff = Column(
        Numeric(precision=20, scale=10), 
        nullable=True,
        comment='Absolute difference between calculated and raw values'
    )
    updated_at = Column(
        TIMESTAMP, 
        server_default=text('CURRENT_TIMESTAMP'),
        nullable=False,
        comment='Last update timestamp'
    )
    
    # Relationship to model
    model = relationship('Model', back_populates='cells')
    
    def __repr__(self):
        return f"<Cell(model_id={self.model_id}, sheet='{self.sheet_name}', cell='{self.cell}')>"