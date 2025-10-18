"""
Unit tests for FormulaParser cell reference conversion utilities.

Tests cover conversion between Excel cell addresses and zero-based coordinates,
range parsing, and sheet name handling.
"""

import pytest
from services.formula_service import FormulaParser


class TestCellToCoordinates:
    """Test cell_to_coordinates() method."""
    
    def test_simple_cells(self):
        """Test basic cell references."""
        assert FormulaParser.cell_to_coordinates('A1') == (0, 0)
        assert FormulaParser.cell_to_coordinates('B1') == (0, 1)
        assert FormulaParser.cell_to_coordinates('A2') == (1, 0)
        assert FormulaParser.cell_to_coordinates('Z1') == (0, 25)
    
    def test_two_letter_columns(self):
        """Test two-letter column references."""
        assert FormulaParser.cell_to_coordinates('AA1') == (0, 26)
        assert FormulaParser.cell_to_coordinates('AB1') == (0, 27)
        assert FormulaParser.cell_to_coordinates('AZ1') == (0, 51)
        assert FormulaParser.cell_to_coordinates('BA1') == (0, 52)
    
    def test_three_letter_columns(self):
        """Test three-letter column references."""
        assert FormulaParser.cell_to_coordinates('AAA1') == (0, 702)
        assert FormulaParser.cell_to_coordinates('ZZZ1') == (0, 18277)
    
    def test_large_row_numbers(self):
        """Test large row numbers."""
        assert FormulaParser.cell_to_coordinates('A100') == (99, 0)
        assert FormulaParser.cell_to_coordinates('B1000') == (999, 1)
        assert FormulaParser.cell_to_coordinates('AA10000') == (9999, 26)
    
    def test_with_sheet_name(self):
        """Test cell references with sheet names."""
        assert FormulaParser.cell_to_coordinates('Sheet1!A1') == (0, 0)
        assert FormulaParser.cell_to_coordinates('MySheet!B24') == (23, 1)
        assert FormulaParser.cell_to_coordinates('Data!AA100') == (99, 26)
    
    def test_case_insensitive(self):
        """Test that lowercase letters are handled."""
        assert FormulaParser.cell_to_coordinates('a1') == (0, 0)
        assert FormulaParser.cell_to_coordinates('aa100') == (99, 26)
    
    def test_invalid_formats(self):
        """Test error handling for invalid formats."""
        with pytest.raises(ValueError):
            FormulaParser.cell_to_coordinates('123')  # No column
        
        with pytest.raises(ValueError):
            FormulaParser.cell_to_coordinates('ABC')  # No row
        
        with pytest.raises(ValueError):
            FormulaParser.cell_to_coordinates('A')  # Incomplete
        
        with pytest.raises(ValueError):
            FormulaParser.cell_to_coordinates('')  # Empty


class TestCoordinatesToCell:
    """Test coordinates_to_cell() method."""
    
    def test_simple_coordinates(self):
        """Test basic coordinate conversions."""
        assert FormulaParser.coordinates_to_cell(0, 0) == 'A1'
        assert FormulaParser.coordinates_to_cell(0, 1) == 'B1'
        assert FormulaParser.coordinates_to_cell(1, 0) == 'A2'
        assert FormulaParser.coordinates_to_cell(0, 25) == 'Z1'
    
    def test_two_letter_columns(self):
        """Test two-letter column generation."""
        assert FormulaParser.coordinates_to_cell(0, 26) == 'AA1'
        assert FormulaParser.coordinates_to_cell(0, 27) == 'AB1'
        assert FormulaParser.coordinates_to_cell(0, 51) == 'AZ1'
        assert FormulaParser.coordinates_to_cell(0, 52) == 'BA1'
    
    def test_three_letter_columns(self):
        """Test three-letter column generation."""
        assert FormulaParser.coordinates_to_cell(0, 702) == 'AAA1'
        assert FormulaParser.coordinates_to_cell(0, 18277) == 'ZZZ1'
    
    def test_large_rows(self):
        """Test large row numbers."""
        assert FormulaParser.coordinates_to_cell(99, 0) == 'A100'
        assert FormulaParser.coordinates_to_cell(999, 1) == 'B1000'
        assert FormulaParser.coordinates_to_cell(9999, 26) == 'AA10000'
    
    def test_negative_coordinates(self):
        """Test error handling for negative coordinates."""
        with pytest.raises(ValueError):
            FormulaParser.coordinates_to_cell(-1, 0)
        
        with pytest.raises(ValueError):
            FormulaParser.coordinates_to_cell(0, -1)
        
        with pytest.raises(ValueError):
            FormulaParser.coordinates_to_cell(-1, -1)


class TestRoundTripConversion:
    """Test that coordinate conversions are reversible."""
    
    def test_round_trip_simple(self):
        """Test round-trip conversion for simple cells."""
        cells = ['A1', 'B24', 'Z1', 'AA100', 'ZZ999']
        for cell in cells:
            row, col = FormulaParser.cell_to_coordinates(cell)
            result = FormulaParser.coordinates_to_cell(row, col)
            assert result == cell, f"Round-trip failed for {cell}"
    
    def test_round_trip_coordinates(self):
        """Test round-trip conversion for coordinates."""
        coords = [(0, 0), (23, 1), (0, 25), (99, 26), (998, 701)]
        for row, col in coords:
            cell = FormulaParser.coordinates_to_cell(row, col)
            result = FormulaParser.cell_to_coordinates(cell)
            assert result == (row, col), f"Round-trip failed for ({row}, {col})"


class TestParseRange:
    """Test parse_range() method."""
    
    def test_simple_ranges(self):
        """Test basic range parsing."""
        assert FormulaParser.parse_range('A1:B10') == ((0, 0), (9, 1))
        assert FormulaParser.parse_range('C5:D15') == ((4, 2), (14, 3))
        assert FormulaParser.parse_range('Z1:Z100') == ((0, 25), (99, 25))
    
    def test_single_cell_range(self):
        """Test range with same start and end."""
        assert FormulaParser.parse_range('A1:A1') == ((0, 0), (0, 0))
        assert FormulaParser.parse_range('B5:B5') == ((4, 1), (4, 1))
    
    def test_large_ranges(self):
        """Test large range references."""
        assert FormulaParser.parse_range('A1:Z100') == ((0, 0), (99, 25))
        assert FormulaParser.parse_range('AA1:AZ1000') == ((0, 26), (999, 51))
    
    def test_range_with_sheet(self):
        """Test range parsing with sheet name."""
        assert FormulaParser.parse_range('Sheet1!A1:B10') == ((0, 0), (9, 1))
        assert FormulaParser.parse_range('Data!C5:D15') == ((4, 2), (14, 3))
    
    def test_invalid_ranges(self):
        """Test error handling for invalid ranges."""
        with pytest.raises(ValueError):
            FormulaParser.parse_range('A1')  # Missing colon
        
        with pytest.raises(ValueError):
            FormulaParser.parse_range('A1:B10:C20')  # Too many colons
        
        with pytest.raises(ValueError):
            FormulaParser.parse_range(':B10')  # Missing start
        
        with pytest.raises(ValueError):
            FormulaParser.parse_range('A1:')  # Missing end


class TestParseCellReference:
    """Test parse_cell_reference() method."""
    
    def test_without_sheet(self):
        """Test cell references without sheet names."""
        assert FormulaParser.parse_cell_reference('A1') == (None, 'A1')
        assert FormulaParser.parse_cell_reference('B24') == (None, 'B24')
        assert FormulaParser.parse_cell_reference('AA100') == (None, 'AA100')
    
    def test_with_sheet(self):
        """Test cell references with sheet names."""
        assert FormulaParser.parse_cell_reference('Sheet1!A1') == ('Sheet1', 'A1')
        assert FormulaParser.parse_cell_reference('MySheet!B24') == ('MySheet', 'B24')
        assert FormulaParser.parse_cell_reference('Data Sheet!AA100') == ('Data Sheet', 'AA100')
    
    def test_sheet_with_spaces(self):
        """Test sheet names with spaces."""
        assert FormulaParser.parse_cell_reference('My Sheet!A1') == ('My Sheet', 'A1')
        assert FormulaParser.parse_cell_reference('Data Analysis!B5') == ('Data Analysis', 'B5')


class TestExistingMethods:
    """Test that existing methods still work after additions."""
    
    def test_extract_dependencies(self):
        """Test dependency extraction still works."""
        deps = FormulaParser.extract_dependencies('=A1+B2', 'Sheet1')
        assert 'Sheet1!A1' in deps
        assert 'Sheet1!B2' in deps
    
    def test_is_text_formula(self):
        """Test text formula detection still works."""
        assert FormulaParser.is_text_formula('=""') is True
        assert FormulaParser.is_text_formula('="Hello"') is True
        assert FormulaParser.is_text_formula('=SUM(A1:A10)') is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])