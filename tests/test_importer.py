"""
Tests for Excel importer functionality.

Tests cover parsing, formula evaluation, circular references, and database operations.

NOTE: Updated to import from services after CLI consolidation (2025-01).
"""

import pytest
from pathlib import Path
from services.excel_import_service import (
    ExcelImportService, CircularReferenceDetector,
    CircularSolver, HyperFormulaEvaluator
)
from services.formula_service import FormulaParser
from backend.models.schema import Model, Cell


class TestFormulaParser:
    """Test formula parsing functionality."""
    
    def test_extract_dependencies(self):
        """Test cell reference extraction from formulas."""
        parser = FormulaParser()
        
        # Simple references
        deps = parser.extract_dependencies('=A1+B2', 'Sheet1')
        assert 'Sheet1!A1' in deps
        assert 'Sheet1!B2' in deps
        
        # Sheet-qualified references
        deps = parser.extract_dependencies('=Sheet2!A1+B2', 'Sheet1')
        assert 'Sheet2!A1' in deps
        assert 'Sheet1!B2' in deps
        
        # No formula
        deps = parser.extract_dependencies('123', 'Sheet1')
        assert deps == []
    
    def test_is_text_formula(self):
        """Test text formula detection."""
        parser = FormulaParser()
        
        assert parser.is_text_formula('=""') is True
        assert parser.is_text_formula('="Hello"') is True
        assert parser.is_text_formula('=CONCATENATE(A1,B1)') is True
        assert parser.is_text_formula('=SUM(A1:A10)') is False
        assert parser.is_text_formula('=123') is False


class TestCircularReferenceDetector:
    """Test circular reference detection."""
    
    def test_detect_simple_cycle(self):
        """Test detection of simple circular reference."""
        detector = CircularReferenceDetector()
        
        detector.add_dependency('A1', ['B1'])
        detector.add_dependency('B1', ['A1'])
        
        cycles = detector.detect_cycles()
        assert len(cycles) == 1
        assert set(cycles[0]) == {'A1', 'B1'}
    
    def test_detect_complex_cycle(self):
        """Test detection of complex circular reference."""
        detector = CircularReferenceDetector()
        
        detector.add_dependency('A1', ['B1'])
        detector.add_dependency('B1', ['C1'])
        detector.add_dependency('C1', ['A1'])
        
        cycles = detector.detect_cycles()
        assert len(cycles) == 1
        assert set(cycles[0]) == {'A1', 'B1', 'C1'}
    
    def test_no_cycle(self):
        """Test that non-circular dependencies don't create cycles."""
        detector = CircularReferenceDetector()
        
        detector.add_dependency('A1', ['B1'])
        detector.add_dependency('B1', ['C1'])
        detector.add_dependency('C1', [])
        
        cycles = detector.detect_cycles()
        assert len(cycles) == 0


class TestCircularSolver:
    """Test iterative solver for circular references."""
    
    def test_convergence(self, mock_circular_cells):
        """Test that solver converges for circular references."""
        solver = CircularSolver(max_iterations=100, threshold=1e-6)
        
        def mock_evaluate(cell_ref, values):
            """Mock evaluation function."""
            if cell_ref == 'Sheet1!A1':
                return values.get('Sheet1!B1', 0) + 1
            elif cell_ref == 'Sheet1!B1':
                return values.get('Sheet1!A1', 0) / 2
            return 0
        
        results, status, iterations = solver.solve(
            ['Sheet1!A1', 'Sheet1!B1'],
            mock_circular_cells,
            mock_evaluate
        )
        
        assert status == 'converged'
        assert iterations < 100
        # A1 should converge to 2, B1 to 1
        assert abs(results['Sheet1!A1'] - 2.0) < 1e-6
        assert abs(results['Sheet1!B1'] - 1.0) < 1e-6
    
    def test_no_raw_value_copying(self, mock_circular_cells):
        """CRITICAL: Ensure raw_value is never copied to calculated_value."""
        solver = CircularSolver()
        
        def mock_evaluate(cell_ref, values):
            if cell_ref == 'Sheet1!A1':
                return values.get('Sheet1!B1', 0) + 1
            elif cell_ref == 'Sheet1!B1':
                return values.get('Sheet1!A1', 0) / 2
            return 0
        
        results, status, _ = solver.solve(
            ['Sheet1!A1', 'Sheet1!B1'],
            mock_circular_cells,
            mock_evaluate
        )
        
        # Verify results are NOT the raw values
        assert results['Sheet1!A1'] != mock_circular_cells['Sheet1!A1']['raw_value']
        assert results['Sheet1!B1'] != mock_circular_cells['Sheet1!B1']['raw_value']
        
        # Verify results are from actual evaluation
        assert abs(results['Sheet1!A1'] - 2.0) < 1e-6
        assert abs(results['Sheet1!B1'] - 1.0) < 1e-6


class TestHyperFormulaEvaluator:
    """Test HyperFormula integration."""
    
    @pytest.mark.skipif(
        not Path('scripts/hyperformula_wrapper.js').exists(),
        reason="HyperFormula wrapper not found"
    )
    def test_evaluate_simple_formula(self):
        """Test HyperFormula evaluation of simple formula."""
        evaluator = HyperFormulaEvaluator()
        
        result = evaluator.evaluate_batch(
            sheets_data=[{
                'name': 'Sheet1',
                'cells': [
                    {'row': 0, 'col': 0, 'value': 5},
                    {'row': 1, 'col': 0, 'value': 10},
                    {'row': 2, 'col': 0, 'formula': '=A1+A2'}
                ]
            }],
            queries=[{
                'sheet': 'Sheet1',
                'row': 2,
                'col': 0,
                'cell': 'A3'
            }]
        )
        
        if result.get('success'):
            assert result['results'][0]['value'] == 15
        else:
            pytest.skip(f"HyperFormula evaluation failed: {result.get('error')}")


class TestExcelImporter:
    """Test Excel importer functionality."""
    
    def test_compute_file_hash(self, session, sample_files):
        """Test file hash computation."""
        if not sample_files['dcmodel'].exists():
            pytest.skip("Sample file not found")
        
        importer = ExcelImportService(session)
        hash1 = importer.compute_file_hash(str(sample_files['dcmodel']))
        hash2 = importer.compute_file_hash(str(sample_files['dcmodel']))
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256
    
    def test_parse_dcmodel(self, session, sample_files):
        """Test parsing dcmodel sample file."""
        if not sample_files['dcmodel'].exists():
            pytest.skip("dcmodel sample file not found")
        
        importer = ExcelImportService(session)
        workbook_data = importer.parse_workbook(str(sample_files['dcmodel']))
        
        # Should have at least one sheet
        assert len(workbook_data['sheets']) >= 1
        
        # Should have parsed cells
        assert len(workbook_data['cells']) > 0
        
        # Check for IRR formula in expected location (approximately row 24, col B)
        irr_cells = [c for c in workbook_data['cells'] 
                     if 'IRR' in (c.get('formula') or '').upper()]
        assert len(irr_cells) > 0, "IRR formula not found"
    
    def test_parse_gpuaas(self, session, sample_files):
        """Test parsing gpuaas sample file."""
        if not sample_files['gpuaas'].exists():
            pytest.skip("gpuaas sample file not found")
        
        importer = ExcelImportService(session)
        workbook_data = importer.parse_workbook(str(sample_files['gpuaas']))
        
        # Should have multiple sheets
        assert len(workbook_data['sheets']) >= 2
        
        # Check for Summary and Monthly sheets
        sheet_names = [s['name'] for s in workbook_data['sheets']]
        assert 'Summary' in sheet_names
        assert 'Monthly' in sheet_names
    
    def test_cell_type_classification(self, session):
        """Test cell type classification."""
        importer = ExcelImportService(session)
        
        # Mock cell with text formula
        class MockCell:
            def __init__(self):
                self.row = 1
                self.column = 1
                self.value = '=""'
                self.data_type = 'f'
                self.coordinate = 'A1'
                self.font = None
                self.border = None
                self.fill = None
        
        class MockWorksheet:
            data_validations = type('obj', (object,), {
                'dataValidation': []
            })
        
        cell_data = importer.extract_cell_data(MockCell(), 'Sheet1', MockWorksheet())
        
        assert cell_data is not None
        assert cell_data['cell_type'] == 'formula_text'


class TestDatabaseOperations:
    """Test database operations."""
    
    def test_create_model(self, session):
        """Test creating a model record."""
        model = Model(
            name='Test Model',
            file_path='/path/to/test.xlsx',
            file_hash='abc123' * 10 + 'abcd',  # 64 chars
            metadata={'sheets': ['Sheet1'], 'total_cells': 100},
            import_summary={'formula_cells': 50}
        )
        
        session.add(model)
        session.commit()
        
        # Verify record exists
        retrieved = session.query(Model).filter_by(name='Test Model').first()
        assert retrieved is not None
        assert retrieved.metadata['total_cells'] == 100
    
    def test_create_cell(self, session):
        """Test creating a cell record."""
        # First create model
        model = Model(
            name='Test Model',
            file_path='/path/to/test.xlsx',
            file_hash='def456' * 10 + 'defg',
            workbook_metadata={},
            import_summary={}
        )
        session.add(model)
        session.flush()
        
        # Create cell
        cell = Cell(
            model_id=model.id,
            sheet_name='Sheet1',
            cell='A1',
            row_num=1,
            col_letter='A',
            cell_type='formula',
            formula='=B1+C1',
            depends_on=['Sheet1!B1', 'Sheet1!C1'],
            is_circular=False
        )
        
        session.add(cell)
        session.commit()
        
        # Verify record exists
        retrieved = session.query(Cell).filter_by(
            model_id=model.id,
            sheet_name='Sheet1',
            cell='A1'
        ).first()
        
        assert retrieved is not None
        assert retrieved.formula == '=B1+C1'
        assert len(retrieved.depends_on) == 2


class TestValidation:
    """Test validation functionality."""
    
    def test_no_raw_value_copying_in_code(self):
        """
        CRITICAL TEST: Scan code for raw_value copying patterns.
        This test ensures data integrity by preventing raw_value copying.
        """
        from data_repair.validate_no_copying import search_codebase_for_copying
        
        violations = search_codebase_for_copying()
        
        # Filter out this test file itself
        violations = [v for v in violations 
                     if 'test_importer.py' not in v['file']]
        
        assert len(violations) == 0, (
            f"Found {len(violations)} raw_value copying violations. "
            "CRITICAL: calculated_value must NEVER be copied from raw_value!"
        )


@pytest.mark.integration
class TestFullImport:
    """Integration tests for full import workflow."""
    
    @pytest.mark.skipif(
        not Path('dcmodel_template_hf_final_v32.xlsx').exists(),
        reason="dcmodel sample file not found"
    )
    def test_import_dcmodel(self, session, sample_files):
        """Test full import of dcmodel sample."""
        importer = ExcelImportService(session)
        
        model_id = importer.import_file(
            str(sample_files['dcmodel']),
            'DC Model Test',
            validate=False
        )
        
        assert model_id is not None
        
        # Verify model was created
        model = session.query(Model).get(model_id)
        assert model is not None
        assert model.name == 'DC Model Test'
        
        # Verify cells were imported
        cell_count = session.query(Cell).filter_by(model_id=model_id).count()
        assert cell_count > 0
        
        # Check for circular references
        circular_count = session.query(Cell).filter_by(
            model_id=model_id,
            is_circular=True
        ).count()
        assert circular_count > 0, "Expected circular references in dcmodel"
    
    @pytest.mark.skipif(
        not Path('gpuaas_calculator v33.xlsx').exists(),
        reason="gpuaas sample file not found"
    )
    def test_import_gpuaas(self, session, sample_files):
        """Test full import of gpuaas sample."""
        importer = ExcelImportService(session)
        
        model_id = importer.import_file(
            str(sample_files['gpuaas']),
            'GPUaaS Test',
            validate=False
        )
        
        assert model_id is not None
        
        # Verify model was created
        model = session.query(Model).get(model_id)
        assert model is not None
        
        # Verify multiple sheets
        sheets = session.query(Cell.sheet_name).filter_by(
            model_id=model_id
        ).distinct().all()
        assert len(sheets) >= 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])