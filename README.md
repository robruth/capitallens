# Excel to PostgreSQL Import System

A production-ready Python CLI for importing datacenter and GPU-as-a-Service Excel financial models into PostgreSQL with advanced formula evaluation, circular reference handling, and comprehensive validation.

## ✨ Features

- **Complete Excel Parsing**: Extracts cells, formulas, styles, and validation rules
- **Dual Workbook Loading**: Captures both formulas and Excel's computed values
- **Smart Formula Evaluation**: Multi-engine classification (HyperFormula/Custom/Iterative)
- **Circular Reference Solver**: Handles complex interdependencies (98.4% convergence rate)
- **Symmetric Data Validation**: Stores both `raw_value` (numeric) and `raw_text` (text) for complete verification
- **Data Integrity**: NEVER copies raw values - only stores actual calculations or NULL
- **Production Ready**: Alembic migrations, comprehensive logging, error handling, diagnostic tools

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
npm install -g hyperformula

# 2. Configure environment
cp .env.example .env
# Edit .env: DATABASE_URL=postgresql://postgres:s3cr3t@localhost/dcmodel

# 3. Set up database
alembic upgrade head

# 4. Import Excel file
python scripts/excel_importer.py import \
  --file dcmodel_template_hf_final_v32.xlsx \
  --name "DC Model" \
  --validate
```

## 📖 Documentation

- **[Quick Start Guide](docs/QUICKSTART.md)** - Get running in 10 minutes
- **[Architecture Documentation](docs/ARCHITECTURE.md)** - System design and implementation details

## 🏗️ Architecture

### Database Schema

**Models Table:**
- Stores workbook metadata (`workbook_metadata` JSONB)
- File hash for duplicate detection
- Import statistics (`import_summary` JSONB)

**Cell Table:**
- Composite PK: `(model_id, sheet_name, row_num, col_letter)`
- **Symmetric verification fields:**
  - `raw_value` (NUMERIC) - Excel's computed numeric value
  - `raw_text` (TEXT) - Excel's computed text value
  - `calculated_value` (NUMERIC) - Our calculated numeric result
  - `calculated_text` (TEXT) - Our calculated text result
- Formula dependencies (JSONB array with GIN index)
- Circular reference tracking
- Style information (JSONB)
- Validation rules (JSONB)

### Formula Evaluation Pipeline

```
1. Parse Excel (dual loading: formulas + values)
2. Extract Dependencies → Build dependency graph
3. Detect Circular References → Strongly connected components
4. Classify Formulas:
   - HyperFormula-compatible (SUM, NPV, IF, etc.)
   - Custom functions (IRR, XIRR, XNPV)
   - Text formulas (="", ="text", CONCATENATE)
5. Evaluate:
   - Non-circular → Direct evaluation
   - Circular → Iterative solver (max 100 iterations, threshold 1e-6)
6. Validate → Compare calculated vs raw (tolerance 1e-6 numeric, exact text)
7. Store → NULL if evaluation fails (never copy raw values)
```

## 📦 Project Structure

```
capitallens/
├── backend/models/schema.py       # SQLAlchemy ORM models
├── scripts/
│   ├── excel_importer.py          # Main CLI (1,047 lines)
│   └── hyperformula_wrapper.js    # Node.js HyperFormula interface
├── data_repair/
│   ├── diagnose_nulls.py          # Diagnostic tool for NULL values
│   ├── fix_null_calculated_values.py  # Re-evaluation utility
│   └── validate_no_copying.py     # Integrity audit (no raw_value copying)
├── alembic/
│   └── versions/001_initial_schema.py  # Database migration
├── tests/
│   ├── conftest.py                # Pytest fixtures
│   └── test_importer.py           # Comprehensive test suite
├── docs/
│   ├── QUICKSTART.md              # Quick start guide
│   └── ARCHITECTURE.md            # Architecture documentation
├── .env.example                   # Environment template
├── requirements.txt               # Python dependencies
└── alembic.ini                    # Migration configuration
```

## 🔧 CLI Commands

### Import Workbook

```bash
python scripts/excel_importer.py import \
  --file <excel-file> \
  --name "Model Name" \
  [--validate]
```

**Options:**
- `--file, -f`: Path to Excel file (required)
- `--name, -n`: Model name for database (required)
- `--validate`: Run post-import validation

**Example:**
```bash
python scripts/excel_importer.py import \
  --file dcmodel_template_hf_final_v32.xlsx \
  --name "DC Model Production" \
  --validate
```

### Validate Existing Model

```bash
python scripts/excel_importer.py validate --model-id 1
```

### Diagnostic Tools

```bash
# Analyze NULL calculated values
python data_repair/diagnose_nulls.py --model-id 1

# Fix NULL values (re-evaluate formulas)
python data_repair/fix_null_calculated_values.py --model-id 1

# Audit for raw_value copying (critical integrity check)
python data_repair/validate_no_copying.py --verbose
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=scripts --cov=backend --cov-report=html

# Critical integrity test
pytest data_repair/validate_no_copying.py::test_no_raw_value_copying -v
```

## 📊 Sample Results

### DC Model (dcmodel_template_hf_final_v32.xlsx)
- Total cells: ~758
- Formula cells: ~617
- Circular references: 122 (120 converged, 2 failed = correct)
- HyperFormula-compatible: 495
- Expected IRR in B24: ~0.1701 (17.01%)

### GPUaaS Calculator (gpuaas_calculator v33.xlsx)
- Multi-sheet (Summary, Monthly)
- Cross-sheet formula dependencies
- Expected Summary IRR (D4): ~0.4608 (46.08%)

## 🎯 Key Design Principles

### 1. Symmetric Validation

```sql
-- Numeric verification
SELECT * FROM cell 
WHERE raw_value IS NOT NULL 
  AND calculated_value IS NOT NULL
  AND ABS(calculated_value - raw_value) > 1e-6;

-- Text verification
SELECT * FROM cell 
WHERE raw_text IS NOT NULL 
  AND calculated_text IS NOT NULL
  AND calculated_text != raw_text;
```

### 2. NO Raw Value Copying

**CRITICAL**: The system NEVER copies `raw_value` to `calculated_value` or `raw_text` to `calculated_text`.

- Formula cells: Evaluated and compared against raw values
- If evaluation fails: Store NULL (not raw value)
- Validated by: `python data_repair/validate_no_copying.py`

### 3. Circular Reference Handling

- Detection: networkx strongly connected components
- Solver: Iterative convergence (max 100 iterations)
- Success rate: 98.4% (120/122 in dcmodel)
- Failed convergence: NULL (correct behavior)

## 🛠️ Technology Stack

- **Python 3.10+** - Core language
- **PostgreSQL 15** - Database with JSONB support
- **SQLAlchemy 2.0** - ORM with declarative models
- **Alembic** - Database migrations
- **openpyxl** - Excel file parsing
- **HyperFormula (Node.js)** - Excel-compatible formula evaluation
- **networkx** - Dependency graph analysis
- **click** - CLI interface
- **pytest** - Testing framework

## 🔍 Database Queries

```sql
-- Check import statistics
SELECT 
  id,
  name,
  workbook_metadata->>'total_cells' as cells,
  workbook_metadata->>'formula_cells' as formulas
FROM models;

-- Find cells with formulas
SELECT sheet_name, cell, formula, calculated_value
FROM cell
WHERE model_id = 1 AND formula IS NOT NULL
LIMIT 10;

-- Check circular references
SELECT COUNT(*) as circular_cells
FROM cell
WHERE model_id = 1 AND is_circular = true;

-- Verify no NULL calculated values (post-fix)
SELECT 
  calculation_engine,
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE calculated_value IS NOT NULL OR calculated_text IS NOT NULL) as populated
FROM cell
WHERE model_id = 1 AND formula IS NOT NULL
GROUP BY calculation_engine;
```

## 🐛 Troubleshooting

### HyperFormula Not Found
```bash
npm install -g hyperformula
```

### Database Connection Error
```bash
# Check PostgreSQL
pg_isready

# Using Docker:
docker start postgres-dcmodel

# Using Homebrew (macOS):
brew services start postgresql@15
```

### Style Extraction Warnings
Some cells may have invalid RGB color values from Excel. The system handles these gracefully by setting `bg_color` to NULL.

### Text Cells with NULL raw_value
This is correct! Text values are stored in `raw_text`, not `raw_value` (which is NUMERIC).

## 📈 Performance

| Operation | 1K Cells | 10K Cells |
|-----------|----------|-----------|
| Parse | <1s | ~3s |
| Evaluate | ~2s | ~20s |
| Insert | <1s | ~5s |
| **Total** | **~3s** | **~28s** |

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Write tests for new functionality
4. Ensure `pytest` passes
5. Run `python data_repair/validate_no_copying.py`
6. Submit pull request

## 📄 License

MIT License

## 🙏 Acknowledgments

Built for datacenter and GPU-as-a-Service financial modeling with:
- [openpyxl](https://openpyxl.readthedocs.io/) - Excel parsing
- [HyperFormula](https://handsontable.github.io/hyperformula/) - Formula evaluation
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database ORM
- [networkx](https://networkx.org/) - Graph analysis

---

**Status**: ✅ Production Ready | **Documentation**: [Quick Start](docs/QUICKSTART.md) | [Architecture](docs/ARCHITECTURE.md)