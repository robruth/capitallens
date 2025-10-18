# Excel to PostgreSQL Import System - Architecture

## Overview

This system imports Excel workbooks into PostgreSQL, preserving formulas, dependencies, and enabling comprehensive validation of calculations.

## Database Schema

### Models Table

Stores workbook-level metadata and import statistics.

```sql
CREATE TABLE models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    file_path VARCHAR(512),
    file_hash VARCHAR(64) NOT NULL UNIQUE,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    workbook_metadata JSONB DEFAULT '{}',
    import_summary JSONB DEFAULT '{}'
);

CREATE INDEX idx_models_hash ON models(file_hash);
CREATE INDEX idx_models_uploaded_at ON models(uploaded_at);
```

**workbook_metadata Structure:**
```json
{
    "sheets": ["Sheet1", "Summary"],
    "sheet_count": 2,
    "total_cells": 758,
    "formula_cells": 617,
    "dropdown_cells": ["Sheet1!B2", "Sheet1!B28"]
}
```

**import_summary Structure:**
```json
{
    "total_cells": 758,
    "formula_cells": 617,
    "circular_references": 122,
    "circular_converged": 120,
    "circular_failed": 2,
    "hyperformula_compatible": 495,
    "python_required": 0,
    "exact_matches": 610,
    "within_tolerance": 5,
    "mismatches": 2,
    "tolerance_used": 1e-6,
    "import_timestamp": "2025-10-15T00:00:00"
}
```

### Cell Table

Stores individual cell data with comprehensive metadata.

```sql
CREATE TABLE cell (
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    sheet_name VARCHAR(255) NOT NULL,
    row_num INTEGER NOT NULL,
    col_letter VARCHAR(10) NOT NULL,
    cell VARCHAR(10) NOT NULL,
    
    -- Cell type and content
    cell_type VARCHAR(20) CHECK (cell_type IN ('value', 'formula', 'formula_text')),
    raw_value NUMERIC(20,10),      -- Excel's computed numeric value
    raw_text TEXT,                  -- Excel's computed text value
    formula TEXT,
    data_type VARCHAR(20) DEFAULT 'text' CHECK (data_type IN ('number', 'text', 'date', 'boolean')),
    
    -- Dependencies and circular references
    depends_on JSONB DEFAULT '[]',
    is_circular BOOLEAN DEFAULT FALSE,
    
    -- Validation
    has_validation BOOLEAN DEFAULT FALSE,
    validation_type VARCHAR(50),
    validation_options JSONB DEFAULT '[]',
    
    -- Calculation
    calculation_engine VARCHAR(20) DEFAULT 'none' CHECK (calculation_engine IN ('none', 'hyperformula', 'custom')),
    converted_formula TEXT,
    calculated_value NUMERIC(20,10),   -- Our calculated numeric result
    calculated_text TEXT,               -- Our calculated text result
    
    -- Style and validation
    style JSONB DEFAULT '{}',
    has_mismatch BOOLEAN DEFAULT FALSE,
    mismatch_diff NUMERIC(20,10),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    PRIMARY KEY (model_id, sheet_name, row_num, col_letter)
);

-- Indexes for performance
CREATE INDEX idx_cell_model_sheet ON cell(model_id, sheet_name);
CREATE INDEX idx_cell_depends_gin ON cell USING GIN(depends_on);
CREATE INDEX idx_cell_engine ON cell(calculation_engine);
CREATE INDEX idx_cell_circular ON cell(is_circular) WHERE is_circular = true;
CREATE INDEX idx_cell_mismatch ON cell(has_mismatch) WHERE has_mismatch = true;
```

## Key Design Principles

### 1. Symmetric Validation

The schema supports verification for both numeric and text data:

**Numeric Data:**
```
raw_value (Excel's result) ↔ calculated_value (our evaluation)
Compare with tolerance: 1e-6
```

**Text Data:**
```
raw_text (Excel's result) ↔ calculated_text (our evaluation)
Compare with exact string match
```

This symmetry ensures complete data integrity verification across all data types.

### 2. NO Raw Value Copying

**CRITICAL POLICY**: The system NEVER copies `raw_value` to `calculated_value` or `raw_text` to `calculated_text`.

- Calculated fields contain ONLY evaluation results
- If evaluation fails: Store NULL (never copy from raw fields)
- Validated by: `data_repair/validate_no_copying.py`

### 3. Dual Workbook Loading

```python
# Load twice to get both formulas and computed values
wb_formulas = openpyxl.load_workbook(file, data_only=False)  # Has formulas
wb_values = openpyxl.load_workbook(file, data_only=True)     # Has Excel's computed values
```

This enables:
- Extract formula text from `wb_formulas`
- Extract Excel's computed result from `wb_values`
- Compare our calculations against Excel's results

## Import Workflow

```
1. Compute SHA256 hash → Check for duplicates
2. Copy file to models/ directory
3. Load workbook twice (formulas + values)
4. For each cell:
   - Extract coordinates, formula, style
   - Get raw_value (numeric) or raw_text (text) from wb_values
   - Classify cell_type (value/formula/formula_text)
   - Extract dependencies from formula
   - Detect data validation rules
5. Build dependency graph (networkx DiGraph)
6. Detect circular references (strongly connected components)
7. Classify formulas by engine:
   - HyperFormula-compatible (SUM, NPV, IF, etc.)
   - Custom (IRR, XIRR, XNPV)
8. Evaluate formulas:
   - Non-circular → Direct evaluation
   - Circular → Iterative solver
9. Compare calculated vs raw → Detect mismatches
10. Bulk insert cells (batches of 1000)
11. Update import_summary statistics
12. Optional: Run post-import validation
```

## Formula Evaluation

### Cell Type Classification

```python
def classify_cell_type(cell_value, formula):
    if not formula:
        return 'value'
    
    if is_text_formula(formula):  # ="" or ="text"
        return 'formula_text'
    
    return 'formula'
```

### Engine Classification

**HyperFormula-Compatible:**
- SUM, AVERAGE, IF, NPV, RATE, PMT, etc.
- Standard Excel functions
- Sets `calculation_engine = 'hyperformula'`

**Custom Functions:**
- IRR, XIRR, XNPV, MIRR
- Requires custom Python implementation
- Sets `calculation_engine = 'custom'`

**Circular References:**
- Any formula in strongly connected component
- Uses iterative solver
- Sets `calculation_engine = 'custom'`

### Circular Reference Solver

```python
class CircularSolver:
    MAX_ITERATIONS = 100
    CONVERGENCE_THRESHOLD = 1e-6
    
    def solve(self, circular_cells, cell_data, evaluate_func):
        # Initialize with zeros (numeric) or empty strings (text)
        values = {cell: 0.0 for cell in circular_cells}
        
        for iteration in range(MAX_ITERATIONS):
            new_values = {}
            max_change = 0
            
            for cell in circular_cells:
                # Evaluate with current context
                result = evaluate_func(cell, values)
                
                if result is None:
                    # CRITICAL: Set NULL, DO NOT copy raw_value
                    new_values[cell] = None
                    continue
                
                change = abs(result - values[cell])
                max_change = max(max_change, change)
                new_values[cell] = result
            
            values = new_values
            
            # Check convergence
            if max_change < CONVERGENCE_THRESHOLD:
                return values, 'converged', iteration + 1
        
        return values, 'max_iterations', MAX_ITERATIONS
```

## Data Validation

### Mismatch Detection

**Numeric Formulas:**
```python
diff = abs(calculated_value - raw_value)
if diff > TOLERANCE:  # 1e-6
    has_mismatch = True
    mismatch_diff = diff
```

**Text Formulas:**
```python
if calculated_text != raw_text:
    has_mismatch = True
    mismatch_diff = abs(len(calculated_text) - len(raw_text))  # Character difference
```

## HyperFormula Integration

### Node.js Wrapper

```javascript
// scripts/hyperformula_wrapper.js
// Reads JSON from stdin, evaluates formulas, outputs JSON

const { HyperFormula } = require('hyperformula');

// Input: { sheets: [...], queries: [...] }
// Output: { success: true, results: [...] }
```

### Python Interface

```python
class HyperFormulaEvaluator:
    def evaluate_batch(self, sheets_data, queries):
        request = {'sheets': sheets_data, 'queries': queries}
        
        process = subprocess.Popen(
            ['node', 'scripts/hyperformula_wrapper.js'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
        )
        
        stdout, _ = process.communicate(json.dumps(request))
        return json.loads(stdout)
```

## Testing Strategy

### Unit Tests

```python
# tests/test_importer.py

def test_circular_convergence():
    """Test iterative solver converges."""
    solver = CircularSolver()
    # Mock circular: A1=B1+1, B1=A1/2
    # Should converge to A1=2, B1=1
    results, status, iters = solver.solve(...)
    assert status == 'converged'
    assert abs(results['A1'] - 2.0) < 1e-6

def test_no_raw_value_copying():
    """CRITICAL: Verify no raw_value copying."""
    violations = search_codebase_for_copying()
    assert len(violations) == 0
```

### Integration Tests

```python
def test_import_dcmodel(session):
    """Test full import of sample file."""
    importer = ExcelImporter(session)
    model_id = importer.import_file('dcmodel_template_hf_final_v32.xlsx', 'Test')
    
    # Verify import
    model = session.query(Model).get(model_id)
    assert model.workbook_metadata['total_cells'] > 700
    
    # Check circular solver
    circular_count = session.query(Cell).filter_by(
        model_id=model_id,
        is_circular=True
    ).count()
    assert circular_count > 100  # Expected ~122
```

## Performance Considerations

### Bulk Insert Optimization

```python
BATCH_SIZE = 1000

for i in range(0, len(cells), BATCH_SIZE):
    batch = cells[i:i + BATCH_SIZE]
    session.bulk_save_objects(batch)
    session.flush()
```

### Memory Management

- Dual loading handled efficiently with openpyxl
- Cell data stored in dictionaries until bulk insert
- Generator-based iteration for large workbooks

### Database Indexes

```sql
-- GIN index for fast JSONB queries
CREATE INDEX idx_cell_depends_gin ON cell USING GIN(depends_on);

-- Partial indexes for filtered queries
CREATE INDEX idx_cell_circular ON cell(is_circular) WHERE is_circular = true;
CREATE INDEX idx_cell_null_calculated ON cell(model_id) 
    WHERE calculated_value IS NULL AND formula IS NOT NULL;
```

## Error Handling

### Parse Errors
- Invalid Excel file → Abort with clear error
- ArrayFormula objects → Handle with `.text` attribute
- Invalid RGB colors → Set to NULL with warning

### Evaluation Errors
- Formula cannot be evaluated → Set calculated fields to NULL
- Circular reference fails to converge → NULL (logged)
- Missing dependencies → NULL (logged)

### Database Errors
- Connection failed → Clear error message
- Constraint violation → Rollback transaction
- Duplicate hash → Skip import, return existing model_id

## Logging Strategy

```python
# Levels:
DEBUG:   Cell-by-cell evaluation details, RGB extraction
INFO:    Import progress, statistics, convergence
WARNING: Complex formulas not evaluated, style extraction issues
ERROR:   Evaluation failures, NULL results with formula context
```

## File Organization

```
capitallens/
├── backend/
│   └── models/
│       └── schema.py              # SQLAlchemy models
├── scripts/
│   ├── excel_importer.py          # Consolidated Dual-Mode CLI (533 lines)
│   ├── excel_importer_legacy.py   # Legacy backup (1,056 lines, for reference)
│   └── hyperformula_wrapper.js    # Node.js interface
├── data_repair/
│   ├── diagnose_nulls.py          # Diagnostic tool
│   ├── fix_null_calculated_values.py
│   └── validate_no_copying.py     # Integrity audit
├── alembic/
│   └── versions/
│       └── 001_initial_schema.py  # Initial migration
├── tests/
│   ├── conftest.py                # Fixtures
│   └── test_importer.py           # Test suite
├── docs/
│   ├── QUICKSTART.md              # Quick start guide
│   └── ARCHITECTURE.md            # This file
├── .env.example
├── requirements.txt
└── alembic.ini
```

## Security Considerations

1. **SQL Injection**: Prevented by SQLAlchemy ORM (parameterized queries)
2. **File Validation**: SHA256 hash checking, duplicate prevention
3. **Formula Evaluation**: Subprocess isolation for HyperFormula
4. **Resource Limits**: 30-second timeout on HyperFormula, max 100 iterations for circular solver

## Future Enhancements

### Phase 1 (Current - Production Ready)
- [x] Complete Excel parsing
- [x] Circular reference detection and solving
- [x] Symmetric validation (raw_value + raw_text)
- [x] CLI tools and diagnostics
- [x] Comprehensive testing framework

### Phase 2 (Planned)
- [ ] Full HyperFormula integration for evaluation
- [ ] Custom IRR/XIRR/XNPV implementations
- [ ] Pycel integration for additional verification
- [ ] Topological sort for evaluation order

### Phase 3 (Future)
- [ ] VBA macro extraction (storage only)
- [ ] Chart definitions storage
- [ ] Named ranges support
- [ ] Web UI dashboard
- [ ] REST API

## Technical Notes

### Why Dual Loading?

openpyxl provides two modes:
- `data_only=False`: Returns formulas (e.g., `=SUM(A1:A10)`)
- `data_only=True`: Returns Excel's computed values (e.g., `123.45`)

We need both:
- Formulas → For dependency analysis and re-evaluation
- Computed values → For verification (`raw_value`/`raw_text`)

### Why raw_text Field?

Originally, only `raw_value` existed (NUMERIC type). This created asymmetry:
- Numeric cells: Could compare `calculated_value` vs `raw_value` ✓
- Text cells: Had no Excel reference value ✗

Adding `raw_text` (TEXT type) provides:
- Symmetric validation for all data types
- Ability to verify text formula results
- Complete data integrity verification

### ArrayFormula Handling

openpyxl returns `ArrayFormula` objects for CSE (Ctrl+Shift+Enter) formulas:

```python
if hasattr(cell.value, 'text'):
    formula = cell.value.text  # Extract from ArrayFormula object
else:
    formula = str(cell.value)
```

### Style Extraction Edge Cases

Some Excel files have invalid RGB color validation messages:

```python
if isinstance(rgb, str) and not rgb.startswith('Values must be'):
    style['bg_color'] = rgb
else:
    style['bg_color'] = None  # Skip invalid values
```

## Performance Benchmarks

| Operation | 758 Cells (dcmodel) | 10K Cells (est.) |
|-----------|---------------------|------------------|
| Parse | <1s | ~3s |
| Dependency Graph | <1s | ~2s |
| Evaluation | ~1s | ~15s |
| Insert | <1s | ~5s |
| **Total** | **~3s** | **~25s** |

## Deployment

### Docker Setup

```dockerfile
FROM python:3.10-slim

# Install Node.js
RUN apt-get update && apt-get install -y nodejs npm
RUN npm install -g hyperformula

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "scripts/excel_importer.py", "import"]
```

**Note:** The CLI now supports both direct and API modes via the `--api-url` flag.

### PostgreSQL Setup

```bash
# Docker
docker run -d --name postgres-dcmodel \
  -e POSTGRES_PASSWORD=s3cr3t \
  -e POSTGRES_DB=dcmodel \
  -p 5432:5432 postgres:15

# Homebrew (macOS)
brew install postgresql@15
createdb dcmodel

# Apply migrations
alembic upgrade head
```

---

**Version**: 1.1  
**Last Updated**: 2025-10-15  
**Status**: Production Ready