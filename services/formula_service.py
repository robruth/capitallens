"""
Formula service for parsing and analyzing Excel formulas.

This module provides utilities for formula parsing, dependency extraction,
and formula classification.
"""

import re
from typing import List


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