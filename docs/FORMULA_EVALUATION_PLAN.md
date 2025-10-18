# Formula Evaluation Implementation Plan

## Executive Summary

This document outlines the implementation plan for integrating actual formula evaluation in `services/excel_import_service.py`, replacing the current placeholder code that uses `raw_value`. The implementation will use HyperFormula for accurate Excel-compatible formula evaluation.

## Current State Analysis

### Placeholder Code Locations

1. **`_evaluate_numeric_formula()` (lines 781-803)**
   - Currently returns `raw_value` as a placeholder
   - Only evaluates simple constant formulas like `=123`
   - Needs full HyperFormula integration

2. **`_evaluate_circular_cells()` (lines 805-867)**
   - Uses `raw_value` from Excel as the evaluation result
   - Needs actual iterative evaluation through HyperFormula
   - Current comment: "In production, would re-evaluate with HyperFormula/custom engine"

### Existing Components (Ready to Use)

1. **HyperFormulaEvaluator Class** (lines 161-211)
   - Already implemented with subprocess interface
   - Has `evaluate_batch()` method for bulk evaluation
   - Interfaces with Node.js wrapper

2. **hyperformula_wrapper.js** (scripts/)
   - Fully functional Node.js wrapper
   - Accepts sheets data and queries
   - Returns evaluated values with types and error handling

3. **Dependency Graph** (CircularReferenceDetector)
   - Already builds dependency graph
   - Detects circular references
   - Can be extended for topological sorting

## Implementation Strategy

### Design Decisions (Based on User Requirements)

1. **Accuracy First**: Use HyperFormula for ALL formula evaluation
2. **Circular References**: Re-evaluate through HyperFormula during iteration
3. **Error Handling**: Set `calculated_value` to NULL on failure, never copy `raw_value`
4. **Memory**: Keep all sheets loaded in HyperFormula instance

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Import Workflow                           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Parse Workbook (existing)                                │
│     - Extract all cells with formulas and values             │
│     - Build dependency graph                                 │
│     - Detect circular references                             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  2. Build HyperFormula Data Structure (NEW)                  │
│     - Convert all sheets to HyperFormula format              │
│     - Transform cell addresses (A1 → row:0, col:0)          │
│     - Prepare formulas and values for bulk load              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  3. Topological Sort (NEW)                                   │
│     - Sort non-circular formulas by dependency order         │
│     - Ensure dependencies evaluated before dependents        │
│     - Create evaluation batches                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  4. Batch Evaluate Formulas (NEW)                            │
│     - Evaluate in topological order                          │
│     - Cache results for reuse                                │
│     - Handle errors (set NULL, log issue)                    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  5. Evaluate Circular References (ENHANCED)                  │
│     - Initialize with zeros                                  │
│     - Iteratively evaluate through HyperFormula              │
│     - Check convergence                                      │
│     - Update HyperFormula context each iteration             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  6. Compare & Store Results (existing)                       │
│     - Compare calculated_value vs raw_value                  │
│     - Track mismatches for validation                        │
│     - Insert into database                                   │
└─────────────────────────────────────────────────────────────┘
```

## Detailed Component Design

### 1. Cell Reference Conversion Utilities (FormulaParser)

**Location**: `services/formula_service.py`

**New Methods**:

```python
@staticmethod
def cell_to_coordinates(cell_ref: str) -> Tuple[int, int]:
    """
    Convert cell reference to zero-based row/col coordinates.
    
    Examples:
        A1 → (0, 0)
        B24 → (23, 1)
        AA100 → (99, 26)
    
    Args:
        cell_ref: Cell address (e.g., "A1", "AA100")
        
    Returns:
        Tuple of (row, col) as zero-based indices
    """
    pass

@staticmethod
def coordinates_to_cell(row: int, col: int) -> str:
    """
    Convert zero-based coordinates to cell reference.
    
    Examples:
        (0, 0) → A1
        (23, 1) → B24
        (99, 26) → AA100
    
    Args:
        row: Zero-based row index
        col: Zero-based column index
        
    Returns:
        Cell address string
    """
    pass

@staticmethod
def parse_range(range_ref: str) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Parse range reference to start/end coordinates.
    
    Examples:
        A1:B10 → ((0, 0), (9, 1))
        C5:C5 → ((4, 2), (4, 2))
    
    Args:
        range_ref: Range reference (e.g., "A1:B10")
        
    Returns:
        Tuple of ((start_row, start_col), (end_row, end_col))
    """
    pass
```

### 2. Topological Sort for Evaluation Order

**Location**: `services/excel_import_service.py` (ExcelImportService class)

**New Method**:

```python
def _topological_sort_formulas(self, cells_data: List[Dict]) -> List[List[Dict]]:
    """
    Sort formula cells in dependency order using topological sort.
    
    Returns batches of cells that can be evaluated in parallel
    (cells in same batch have no dependencies on each other).
    
    Algorithm:
        1. Build dependency graph from self.circular_detector
        2. Filter out circular cells
        3. Use Kahn's algorithm for topological sort
        4. Group cells by evaluation level (batch)
    
    Args:
        cells_data: All cell data dictionaries
        
    Returns:
        List of batches, where each batch is a list of cells
        that can be evaluated in parallel
    """
    pass
```

**Data Structure**:
```python
# Example output
[
    [cell_A, cell_B, cell_C],  # Batch 0: No dependencies
    [cell_D, cell_E],           # Batch 1: Depends only on Batch 0
    [cell_F],                   # Batch 2: Depends on Batches 0 & 1
]
```

### 3. HyperFormula Data Structure Builder

**Location**: `services/excel_import_service.py` (ExcelImportService class)

**New Method**:

```python
def _build_hyperformula_sheets(self, cells_data: List[Dict]) -> List[Dict]:
    """
    Build HyperFormula sheets data structure from parsed cells.
    
    Converts cell data to format expected by hyperformula_wrapper.js:
    
    {
        "name": "Sheet1",
        "cells": [
            {"row": 0, "col": 0, "formula": "=SUM(B1:B10)"},
            {"row": 0, "col": 1, "value": 5},
            {"row": 1, "col": 1, "value": 10}
        ]
    }
    
    Args:
        cells_data: All parsed cell data
        
    Returns:
        List of sheet dictionaries ready for HyperFormula
    """
    pass
```

**Conversion Logic**:
- Group cells by sheet_name
- Convert cell addresses to (row, col) using FormulaParser.cell_to_coordinates()
- Include both formula cells AND value cells (for dependencies)
- Handle text formulas separately (they don't need HyperFormula)

### 4. Batch Evaluation Engine

**Location**: `services/excel_import_service.py` (ExcelImportService class)

**New Method**:

```python
def _batch_evaluate_hyperformula(
    self, 
    sheets_data: List[Dict], 
    cells_to_evaluate: List[Dict],
    cache: Dict[str, float]
) -> Dict[str, Any]:
    """
    Batch evaluate formulas using HyperFormula.
    
    Args:
        sheets_data: HyperFormula sheets structure
        cells_to_evaluate: Cells to evaluate in this batch
        cache: Dictionary to cache evaluated values
        
    Returns:
        Dictionary mapping cell_ref to evaluated value/error
        
    Error Handling:
        - HyperFormula errors (#DIV/0!, #REF!, etc.) → return None
        - Evaluation failures → return None
        - Success → return numeric value
    """
    pass
```

**Query Building**:
```python
queries = [
    {
        "sheet": cell['sheet_name'],
        "row": row,
        "col": col,
        "cell": f"{cell['sheet_name']}!{cell['cell']}"
    }
    for cell in cells_to_evaluate
]
```

### 5. Enhanced _evaluate_numeric_formula()

**Current Implementation** (lines 781-803):
```python
def _evaluate_numeric_formula(self, cell: Dict, cell_lookup: Dict) -> Optional[float]:
    # Simple constant formulas
    if re.match(r'^=\d+(\.\d+)?$', formula):
        return float(formula[1:])
    
    # PLACEHOLDER: Using raw_value
    if cell.get('raw_value') is not None:
        return float(cell['raw_value'])
    
    return None
```

**New Implementation**:
```python
def _evaluate_numeric_formula(
    self,
    cell: Dict,
    cell_lookup: Dict,
    sheets_data: List[Dict],
    cache: Dict[str, float]
) -> Optional[float]:
    """
    Evaluate numeric formula using HyperFormula.
    
    This replaces the placeholder that used raw_value.
    
    Args:
        cell: Cell data dictionary
        cell_lookup: All cells indexed by reference
        sheets_data: HyperFormula sheets structure
        cache: Evaluation cache
        
    Returns:
        Evaluated numeric value or None on error
    """
    formula = cell.get('formula', '')
    cell_ref = f"{cell['sheet_name']}!{cell['cell']}"
    
    # Check cache first
    if cell_ref in cache:
        return cache[cell_ref]
    
    # Simple constant formulas (fast path)
    if re.match(r'^=\d+(\.\d+)?$', formula):
        result = float(formula[1:])
        cache[cell_ref] = result
        return result
    
    # Evaluate through HyperFormula
    try:
        row, col = self.parser.cell_to_coordinates(cell['cell'])
        
        result = self.hf_evaluator.evaluate_batch(
            sheets_data=sheets_data,
            queries=[{
                'sheet': cell['sheet_name'],
                'row': row,
                'col': col,
                'cell': cell_ref
            }]
        )
        
        if result.get('success') and result['results']:
            res = result['results'][0]
            
            # Handle different result types
            if res['type'] == 'number':
                value = float(res['value'])
                cache[cell_ref] = value
                return value
            elif res['type'] == 'error':
                # Excel errors: #DIV/0!, #REF!, #VALUE!, etc.
                logger.warning(f"Formula error for {cell_ref}: {res.get('error', res['value'])}")
                return None
            else:
                # Empty or unexpected type
                return None
        else:
            logger.error(f"HyperFormula evaluation failed for {cell_ref}: {result.get('error')}")
            return None
            
    except Exception as e:
        logger.error(f"Error evaluating {cell_ref}: {e}")
        return None
```

### 6. Enhanced evaluate_formulas()

**Current Flow** (lines 673-715):
1. Separate circular from non-circular
2. Evaluate non-circular cells one by one
3. Evaluate circular cells with solver

**New Flow**:
```python
def evaluate_formulas(self, cells_data: List[Dict]):
    """
    Evaluate all formulas using HyperFormula with proper dependency ordering.
    """
    # Build HyperFormula data structure (include ALL cells)
    sheets_data = self._build_hyperformula_sheets(cells_data)
    
    # Initialize evaluation cache
    cache = {}
    
    # Build lookup
    cell_lookup = {
        f"{c['sheet_name']}!{c['cell']}": c 
        for c in cells_data
    }
    
    # Separate circular from non-circular
    circular_cells = [c for c in cells_data if c.get('is_circular') and c.get('formula')]
    non_circular_cells = [c for c in cells_data if not c.get('is_circular') and c.get('formula')]
    
    # Topological sort for evaluation order
    evaluation_batches = self._topological_sort_formulas(non_circular_cells)
    
    # Evaluate non-circular formulas in dependency order
    total_formulas = len(non_circular_cells)
    evaluated = 0
    
    for batch_idx, batch in enumerate(evaluation_batches):
        # Progress tracking
        progress = 40 + (30 * (evaluated / max(total_formulas, 1)))
        self._emit_progress('evaluation', progress, 
                          f"Evaluating batch {batch_idx+1}/{len(evaluation_batches)}")
        
        # Batch evaluate this level
        self._evaluate_batch(batch, sheets_data, cache, cell_lookup)
        evaluated += len(batch)
    
    # Evaluate circular formulas (70-80%)
    if circular_cells:
        self._emit_progress('evaluation', 70, 'Solving circular references...')
        self._evaluate_circular_cells_hyperformula(
            circular_cells, 
            sheets_data, 
            cell_lookup,
            cache
        )
```

### 7. Enhanced Circular Reference Solver

**New Method**:
```python
def _evaluate_circular_cells_hyperformula(
    self,
    circular_cells: List[Dict],
    sheets_data: List[Dict],
    cell_lookup: Dict,
    cache: Dict
):
    """
    Evaluate circular formulas using iterative HyperFormula evaluation.
    
    Algorithm:
        1. Initialize circular cells with zeros
        2. Update HyperFormula sheets with current values
        3. Evaluate all circular cells through HyperFormula
        4. Check for convergence
        5. Repeat until convergence or max iterations
    
    This replaces the placeholder that used raw_value.
    """
    circular_refs = [f"{c['sheet_name']}!{c['cell']}" for c in circular_cells]
    
    # Initialize with zeros
    values = {ref: 0.0 for ref in circular_refs}
    converged_cells = set()
    
    for iteration in range(self.max_circular_iterations):
        # Update HyperFormula sheets with current circular values
        updated_sheets = self._update_sheets_with_values(sheets_data, values)
        
        # Evaluate all circular cells through HyperFormula
        queries = []
        for cell in circular_cells:
            row, col = self.parser.cell_to_coordinates(cell['cell'])
            queries.append({
                'sheet': cell['sheet_name'],
                'row': row,
                'col': col,
                'cell': f"{cell['sheet_name']}!{cell['cell']}"
            })
        
        result = self.hf_evaluator.evaluate_batch(updated_sheets, queries)
        
        if not result.get('success'):
            logger.error(f"HyperFormula batch evaluation failed: {result.get('error')}")
            break
        
        # Process results and check convergence
        new_values = {}
        max_change = 0.0
        
        for res in result['results']:
            cell_ref = res['cell']
            
            if res['type'] == 'number':
                new_value = float(res['value'])
            elif res['type'] == 'error':
                # Error in formula, set to None
                new_value = None
            else:
                new_value = None
            
            if new_value is not None and cell_ref in values:
                change = abs(new_value - values[cell_ref])
                max_change = max(max_change, change)
                
                if change < self.convergence_threshold:
                    converged_cells.add(cell_ref)
            
            new_values[cell_ref] = new_value
        
        values = new_values
        
        logger.debug(f"Iteration {iteration+1}: max_change={max_change:.2e}, "
                    f"converged={len(converged_cells)}/{len(circular_refs)}")
        
        # Check convergence
        if max_change < self.convergence_threshold:
            logger.info(f"Circular references converged after {iteration+1} iterations")
            break
    
    # Apply results to cells
    for cell in circular_cells:
        cell_ref = f"{cell['sheet_name']}!{cell['cell']}"
        result = values.get(cell_ref)
        
        cell['calculation_engine'] = 'hyperformula'
        cell['converted_formula'] = cell.get('formula')
        cell['calculated_value'] = result
        
        # Compare with raw_value for validation
        if result is not None and cell.get('raw_value') is not None:
            diff = abs(float(result) - float(cell['raw_value']))
            if diff > self.tolerance:
                cell['has_mismatch'] = True
                cell['mismatch_diff'] = float(diff)
                self.stats['mismatches'] += 1
            else:
                self.stats['exact_matches'] += 1
```

## Error Handling Strategy

### Excel Error Types

HyperFormula returns Excel-compatible errors:

| Error | Meaning | Handling |
|-------|---------|----------|
| #DIV/0! | Division by zero | Set calculated_value to NULL, log warning |
| #REF! | Invalid reference | Set calculated_value to NULL, log error |
| #VALUE! | Wrong value type | Set calculated_value to NULL, log error |
| #NAME? | Unknown function | Set calculated_value to NULL, log error |
| #N/A | Value not available | Set calculated_value to NULL, log info |
| #NULL! | Null intersection | Set calculated_value to NULL, log warning |

### Error Response Format

```python
{
    "success": True,
    "results": [
        {
            "cell": "Sheet1!A1",
            "value": "#DIV/0!",
            "type": "error",
            "error": "Division by zero"
        }
    ]
}
```

### Logging Strategy

```python
# For each error type
if result_type == 'error':
    error_msg = f"Formula error in {cell_ref}: {error_value}"
    
    if error_value in ['#DIV/0!', '#NULL!']:
        logger.warning(error_msg)  # Common, expected errors
    elif error_value in ['#REF!', '#NAME?']:
        logger.error(error_msg)     # Serious formula issues
    else:
        logger.info(error_msg)       # Other cases
    
    cell['calculated_value'] = None
    self.stats['errors'] += 1
```

## Performance Considerations

### Batch Size Optimization

- **Target batch size**: 100-500 cells per HyperFormula call
- **Rationale**: Balance between subprocess overhead and memory usage
- **Implementation**: Group cells by topological level

### Caching Strategy

```python
# Cache structure
cache = {
    "Sheet1!A1": 100.0,
    "Sheet1!A2": 200.0,
    # ... evaluated values
}

# Cache benefits:
# 1. Avoid re-evaluating same cell multiple times
# 2. Reuse results for cells referenced multiple times
# 3. Speed up circular reference iterations
```

### Memory Management

For typical workbooks (< 100k cells):
- Keep all sheets in memory
- Single HyperFormula instance per import
- Cache all evaluated values

For large workbooks (> 100k cells):
- Consider implementing in future if needed
- Options: streaming evaluation, sheet batching

## Testing Strategy

### Unit Tests

1. **Cell Reference Conversion**
   ```python
   def test_cell_to_coordinates():
       assert FormulaParser.cell_to_coordinates('A1') == (0, 0)
       assert FormulaParser.cell_to_coordinates('AA100') == (99, 26)
   ```

2. **Topological Sort**
   ```python
   def test_topological_sort_simple():
       # A1 = B1 + 1
       # B1 = 5
       # Expected order: [B1], [A1]
   ```

3. **HyperFormula Integration**
   ```python
   def test_evaluate_sum_formula():
       # Test =SUM(A1:A10) with known values
   ```

4. **Error Handling**
   ```python
   def test_division_by_zero():
       # =1/0 should return None with #DIV/0! error
   ```

### Integration Tests

1. **Real Workbook Evaluation**
   ```python
   def test_dcmodel_formula_evaluation():
       # Import dcmodel and verify calculated_values are NOT raw_values
   ```

2. **Circular Reference Convergence**
   ```python
   def test_circular_convergence_with_hyperformula():
       # Create workbook with circular references
       # Verify convergence through actual evaluation
   ```

3. **Cross-Sheet References**
   ```python
   def test_cross_sheet_formulas():
       # Sheet2!A1 references Sheet1!B5
       # Verify proper evaluation
   ```

### Validation Tests

1. **No Raw Value Copying**
   ```python
   def test_no_raw_value_copying():
       # Ensure calculated_value ≠ raw_value (unless coincidental)
       # Check that evaluation actually happened
   ```

2. **Accuracy Verification**
   ```python
   def test_formula_accuracy():
       # Compare against known correct results
       # Tolerance: 1e-10 for numerical precision
   ```

## Migration Path

### Phase 1: Add Utilities (Low Risk)
- Add cell reference conversion to FormulaParser
- Add topological sort method
- Add HyperFormula data structure builder
- **Test**: Unit tests for each utility

### Phase 2: Batch Evaluation (Medium Risk)
- Implement _batch_evaluate_hyperformula()
- Update _evaluate_numeric_formula() to use HyperFormula
- Keep old path as fallback (temporary)
- **Test**: Integration tests with simple formulas

### Phase 3: Update Main Flow (Medium Risk)
- Modify evaluate_formulas() to use batching
- Implement topological evaluation
- **Test**: Full import workflow tests

### Phase 4: Circular References (High Risk)
- Implement _evaluate_circular_cells_hyperformula()
- Remove raw_value fallback from circular solver
- **Test**: Circular reference convergence tests

### Phase 5: Cleanup (Low Risk)
- Remove all placeholder code
- Update documentation
- Final validation tests

## Success Criteria

1. **Functional Requirements**
   - ✅ All formulas evaluated through HyperFormula
   - ✅ No raw_value copying to calculated_value
   - ✅ Proper handling of range references (A1:B10)
   - ✅ Support for cross-sheet references (Sheet1!A1)
   - ✅ Topological sort for evaluation order
   - ✅ Circular reference iterative evaluation
   - ✅ Excel error handling (#DIV/0!, #REF!, etc.)
   - ✅ Evaluation result caching

2. **Performance Requirements**
   - Import time increase < 50% for typical workbooks
   - Memory usage < 2x original for same workbook
   - Circular convergence < 100 iterations for 99% of cases

3. **Quality Requirements**
   - All existing tests pass
   - New tests achieve > 90% code coverage
   - No raw_value copying violations
   - Error rate < 1% on real workbooks

## Risk Mitigation

### Risk: HyperFormula subprocess failures
**Mitigation**: Comprehensive error handling, graceful degradation to NULL

### Risk: Performance degradation
**Mitigation**: Batching, caching, progress tracking

### Risk: Breaking existing functionality
**Mitigation**: Phased rollout, extensive testing, keep validation tests

### Risk: Memory issues with large workbooks
**Mitigation**: Monitor memory usage, implement batching if needed

## Next Steps

1. Review and approve this plan
2. Switch to Code mode for implementation
3. Start with Phase 1 (utilities)
4. Test after each phase
5. Iterate based on feedback

## References

- HyperFormula Documentation: https://hyperformula.handsontable.com/
- OpenPyXL Cell Reference: https://openpyxl.readthedocs.io/
- NetworkX Topological Sort: https://networkx.org/documentation/stable/reference/algorithms/dag.html