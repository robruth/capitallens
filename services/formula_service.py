"""
Formula service for parsing and analyzing Excel formulas.

This module provides utilities for formula parsing, dependency extraction,
and formula classification.
"""

import re
from typing import List, Tuple, Optional


class FormulaParser:
    """Parse and analyze Excel formulas."""
    
    # Regex to match cell references (e.g., A1, B24, Sheet1!A1)
    CELL_REF_PATTERN = re.compile(r'(?:([A-Za-z0-9_]+)!)?([A-Z]+\d+)')
    
    @staticmethod
    def extract_dependencies(formula: str, current_sheet: str) -> List[str]:
        """
        Extract cell dependencies from a formula.
        
        Args:
            formula: Formula text (e.g., "=SUM(A1:A10)")
            current_sheet: Current sheet name for relative references
        
        Returns:
            List of cell references in format "Sheet!Cell" or "Cell" for same sheet.
        """
        # Convert to string if it's an openpyxl formula object
        if hasattr(formula, 'text'):
            formula = formula.text
        elif not isinstance(formula, str):
            formula = str(formula)
        
        if not formula or not formula.startswith('='):
            return []
        
        dependencies = []
        for match in FormulaParser.CELL_REF_PATTERN.finditer(formula):
            sheet, cell = match.groups()
            if sheet:
                dependencies.append(f"{sheet}!{cell}")
            else:
                dependencies.append(f"{current_sheet}!{cell}")
        
        return dependencies
    
    @staticmethod
    def is_text_formula(formula: str) -> bool:
        """
        Detect if formula returns text (e.g., ="" or ="text").
        
        Args:
            formula: Formula text
            
        Returns:
            True if formula returns text value
        """
        # Convert to string if it's an openpyxl formula object
        if hasattr(formula, 'text'):
            formula = formula.text
        elif not isinstance(formula, str):
            formula = str(formula)
        
        if not formula or not formula.startswith('='):
            return False
        
        # Check for empty string formula
        if formula.strip() == '=""':
            return True
        
        # Check for string literal formula
        if re.match(r'^="[^"]*"$', formula.strip()):
            return True
        
        # Check for text functions
        text_functions = ['CONCATENATE', 'CONCAT', 'TEXT', 'CHAR', 'LOWER', 'UPPER', 'TRIM']
        for func in text_functions:
            if func + '(' in formula.upper():
                return True
        
        return False
    
    @staticmethod
    def is_hyperformula_compatible(formula: str) -> bool:
        """
        Check if formula is compatible with HyperFormula.
        
        Args:
            formula: Formula text
            
        Returns:
            True if formula can be evaluated by HyperFormula
        """
        # List of known incompatible functions
        incompatible = ['IRR', 'XIRR', 'XNPV', 'MIRR']
        formula_upper = formula.upper()
        
        for func in incompatible:
            if func + '(' in formula_upper:
                return False
        
        return True
    
    @staticmethod
    def is_custom_function(formula: str) -> bool:
        """
        Check if formula requires custom implementation.
        
        Args:
            formula: Formula text
            
        Returns:
            True if formula requires custom evaluation
        """
        custom_funcs = ['IRR', 'XIRR', 'XNPV', 'MIRR']
        formula_upper = formula.upper()
        
        for func in custom_funcs:
            if func + '(' in formula_upper:
                return True
        
        return False
    
    @staticmethod
    def convert_for_custom(formula: str) -> str:
        """
        Convert formula for custom evaluation.
        
        Args:
            formula: Original formula text
            
        Returns:
            Converted formula (placeholder for now)
        """
        # Placeholder: would implement formula conversion here
        # e.g., =IRR(B65:V65) → =IRR_CUSTOM(B65:V65)
        return formula
    
    @staticmethod
    def evaluate_text_formula(formula: str) -> str:
        """
        Evaluate simple text formulas.
        
        Args:
            formula: Text formula to evaluate
            
        Returns:
            Evaluated text result, or None if cannot evaluate
        """
        # Handle simple cases
        if formula == '=""':
            return ''
        
        # Extract string literal
        match = re.match(r'^="([^"]*)"$', formula.strip())
        if match:
            return match.group(1)
        
        # For complex text formulas, return None (needs full evaluator)
        return None
    
    @staticmethod
    def cell_to_coordinates(cell_ref: str) -> Tuple[int, int]:
        """
        Convert cell reference to zero-based row/col coordinates.
        
        Handles standard Excel cell references (A1, B24, AA100, etc.).
        
        Examples:
            A1 → (0, 0)
            B24 → (23, 1)
            AA100 → (99, 26)
            Z1 → (0, 25)
        
        Args:
            cell_ref: Cell address (e.g., "A1", "AA100")
            
        Returns:
            Tuple of (row, col) as zero-based indices
            
        Raises:
            ValueError: If cell reference format is invalid
        """
        # Remove sheet name if present (handle "Sheet1!A1" format)
        if '!' in cell_ref:
            cell_ref = cell_ref.split('!')[-1]
        
        # Match column letters and row number
        match = re.match(r'^([A-Z]+)(\d+)$', cell_ref.upper())
        if not match:
            raise ValueError(f"Invalid cell reference: {cell_ref}")
        
        col_letters, row_str = match.groups()
        
        # Convert column letters to zero-based index
        # A=0, B=1, ..., Z=25, AA=26, AB=27, etc.
        col = 0
        for char in col_letters:
            col = col * 26 + (ord(char) - ord('A') + 1)
        col -= 1  # Convert to zero-based
        
        # Convert row to zero-based index
        row = int(row_str) - 1
        
        return (row, col)
    
    @staticmethod
    def coordinates_to_cell(row: int, col: int) -> str:
        """
        Convert zero-based coordinates to cell reference.
        
        Examples:
            (0, 0) → A1
            (23, 1) → B24
            (99, 26) → AA100
            (0, 25) → Z1
        
        Args:
            row: Zero-based row index
            col: Zero-based column index
            
        Returns:
            Cell address string (e.g., "A1", "AA100")
            
        Raises:
            ValueError: If row or col are negative
        """
        if row < 0 or col < 0:
            raise ValueError(f"Row and column must be non-negative: row={row}, col={col}")
        
        # Convert column index to letters
        col_letters = ''
        col_num = col + 1  # Convert to 1-based for calculation
        
        while col_num > 0:
            col_num -= 1  # Adjust for 0-based alphabet
            col_letters = chr(ord('A') + (col_num % 26)) + col_letters
            col_num //= 26
        
        # Convert row index to 1-based row number
        row_num = row + 1
        
        return f"{col_letters}{row_num}"
    
    @staticmethod
    def parse_range(range_ref: str) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Parse range reference to start/end coordinates.
        
        Examples:
            A1:B10 → ((0, 0), (9, 1))
            C5:C5 → ((4, 2), (4, 2))
            AA1:AB100 → ((0, 26), (99, 27))
        
        Args:
            range_ref: Range reference (e.g., "A1:B10", "Sheet1!A1:B10")
            
        Returns:
            Tuple of ((start_row, start_col), (end_row, end_col))
            
        Raises:
            ValueError: If range reference format is invalid
        """
        # Remove sheet name if present
        if '!' in range_ref:
            range_ref = range_ref.split('!')[-1]
        
        # Split range into start and end cells
        if ':' not in range_ref:
            raise ValueError(f"Invalid range reference (missing ':'): {range_ref}")
        
        parts = range_ref.split(':')
        if len(parts) != 2:
            raise ValueError(f"Invalid range reference format: {range_ref}")
        
        start_cell, end_cell = parts
        
        # Convert both cells to coordinates
        start_coords = FormulaParser.cell_to_coordinates(start_cell)
        end_coords = FormulaParser.cell_to_coordinates(end_cell)
        
        return (start_coords, end_coords)
    
    @staticmethod
    def parse_cell_reference(cell_ref: str) -> Tuple[Optional[str], str]:
        """
        Parse a cell reference into sheet name and cell address.
        
        Examples:
            "A1" → (None, "A1")
            "Sheet1!A1" → ("Sheet1", "A1")
            "My Sheet!B5" → ("My Sheet", "B5")
        
        Args:
            cell_ref: Cell reference with optional sheet name
            
        Returns:
            Tuple of (sheet_name, cell_address)
            sheet_name is None if not specified
        """
        if '!' in cell_ref:
            parts = cell_ref.split('!', 1)
            return (parts[0], parts[1])
        else:
            return (None, cell_ref)