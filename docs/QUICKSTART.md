# Quick Start Guide

Get the Excel to PostgreSQL import system running in 10 minutes.

## ⚡ Prerequisites

Verify you have:
- Python 3.10 or higher
- PostgreSQL 12 or higher
- Node.js 14 or higher
- npm (for HyperFormula)

```bash
python3 --version  # Should be 3.10+
psql --version     # Should be 12+
node --version     # Should be 14+
npm --version
```

## 🚀 Installation

### 1. Clone and Setup

```bash
# Clone repository
git clone https://github.com/yourusername/capitallens.git
cd capitallens

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install HyperFormula globally
npm install -g hyperformula
```

### 2. Set Up PostgreSQL

**Option A: Docker (Recommended)**
```bash
docker run -d \
  --name postgres-dcmodel \
  -e POSTGRES_PASSWORD=s3cr3t \
  -e POSTGRES_DB=dcmodel \
  -p 5432:5432 \
  postgres:15

# Wait for startup
sleep 5
```

**Option B: Local PostgreSQL**
```bash
# macOS (Homebrew)
brew install postgresql@15
brew services start postgresql@15
createdb dcmodel

# Ubuntu/Debian
sudo apt install postgresql-15
sudo -u postgres createdb dcmodel
```

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your database credentials
nano .env  # or: vim .env, code .env
```

**Minimum required:**
```bash
DATABASE_URL=postgresql://postgres:s3cr3t@localhost/dcmodel
```

### 4. Run Database Migrations

```bash
# Apply schema (creates models and cell tables)
alembic upgrade head

# You should see:
# INFO [alembic.runtime.migration] Running upgrade -> 001_initial_schema
```

### 5. Verify Installation

```bash
# Test database connection
python -c "from sqlalchemy import create_engine; import os; from dotenv import load_dotenv; load_dotenv(); engine = create_engine(os.getenv('DATABASE_URL')); conn = engine.connect(); print('✓ Database connected'); conn.close()"

# Test HyperFormula (optional - for future use)
echo '{"sheets":[{"name":"S1","cells":[{"row":0,"col":0,"value":5}]}],"queries":[{"sheet":"S1","row":0,"col":0,"cell":"A1"}]}' | node scripts/hyperformula_wrapper.js
# Should output: {"success":true,...}
```

## 🎯 First Import

The CLI supports two modes: **Direct** (local database) and **API** (FastAPI backend).

### Import Sample File (Direct Mode)

```bash
# Direct mode - imports directly to local database
python scripts/excel_importer.py import \
  --file dcmodel_template_hf_final_v32.xlsx \
  --name "DC Model Test" \
  --validate

# Expected output:
# 💾 Direct Mode: Using local database
# ✓ Import successful!
# Model ID: 1
#
# Statistics:
#   Total cells: 758
#   Formula cells: 617
#   Circular references: 122
```

### Import via API Mode (Optional)

If you have the FastAPI backend running:

```bash
# API mode - sends request to FastAPI backend
python scripts/excel_importer.py import \
  --file dcmodel_template_hf_final_v32.xlsx \
  --name "DC Model Test" \
  --api-url http://localhost:8000 \
  --validate

# Expected output:
# 🌐 API Mode: Using backend at http://localhost:8000
# ✓ Upload successful. Job ID: abc-123-def-456
# 🔄 Tracking progress via WebSocket...
# [████████████████████████████████████████] 100.0% - complete: Import complete
# ✓ Import successful!
```

### Check Results

```bash
# View imported models
psql dcmodel -c "SELECT id, name, uploaded_at FROM models;"

# Count cells by type
psql dcmodel -c "
SELECT 
  data_type,
  COUNT(*) as count,
  COUNT(*) FILTER (WHERE raw_value IS NOT NULL) as has_numeric,
  COUNT(*) FILTER (WHERE raw_text IS NOT NULL) as has_text
FROM cell 
WHERE model_id = 1
GROUP BY data_type;
"

# Check formula evaluation
psql dcmodel -c "
SELECT 
  calculation_engine,
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE calculated_value IS NOT NULL) as evaluated
FROM cell 
WHERE model_id = 1 AND formula IS NOT NULL
GROUP BY calculation_engine;
"
```

## 🔍 Explore the Data

### Using psql

```bash
# Connect to database
psql dcmodel

# List all models
SELECT id, name, workbook_metadata->>'total_cells' as cells FROM models;

# Find circular references
SELECT sheet_name, cell, formula 
FROM cell 
WHERE model_id = 1 AND is_circular = true 
LIMIT 5;

# Check text vs numeric split
SELECT 
  COUNT(*) FILTER (WHERE raw_value IS NOT NULL) as numeric_cells,
  COUNT(*) FILTER (WHERE raw_text IS NOT NULL) as text_cells
FROM cell WHERE model_id = 1;
```

### Using Python

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.schema import Model, Cell
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL'))
Session = sessionmaker(bind=engine)
session = Session()

# Get model
model = session.query(Model).first()
print(f"Model: {model.name}")
print(f"Metadata: {model.workbook_metadata}")

# Get sample cells
cells = session.query(Cell).filter_by(model_id=model.id).limit(5).all()
for c in cells:
    print(f"{c.sheet_name}!{c.cell}: {c.formula or c.raw_value or c.raw_text}")

session.close()
```

## 📊 Import Second Sample

**Direct Mode:**
```bash
python scripts/excel_importer.py import \
  --file "gpuaas_calculator v33.xlsx" \
  --name "GPUaaS Calculator" \
  --validate
```

**API Mode:**
```bash
python scripts/excel_importer.py import \
  --file "gpuaas_calculator v33.xlsx" \
  --name "GPUaaS Calculator" \
  --api-url http://localhost:8000 \
  --validate
```

## 🔧 Common Maintenance

### View Logs

```bash
tail -f import.log  # Watch import progress
```

### Backup Database

```bash
pg_dump dcmodel > backup_$(date +%Y%m%d).sql
```

### Reset Database

```bash
# CAUTION: Deletes all data
psql -c "DROP DATABASE dcmodel; CREATE DATABASE dcmodel;"
alembic upgrade head
```

## 🐛 Troubleshooting

### "Module 'backend' not found"
**Solution**: Script adds parent directory to sys.path automatically. Ensure you're running from project root.

### "Permission denied" on scripts
```bash
chmod +x scripts/excel_importer.py
chmod +x data_repair/*.py
```

### "HyperFormula not found"
```bash
npm install -g hyperformula
# Verify: npx hyperformula --version
```

### "Database connection refused"
```bash
# Check PostgreSQL status
pg_isready

# Docker:
docker ps | grep postgres
docker start postgres-dcmodel

# Local:
# macOS: brew services start postgresql@15
# Linux: sudo systemctl start postgresql
```

### Style warnings in JSONB
Some cells may have "Values must be of type <class 'str'>" in bg_color. This is handled by setting bg_color to NULL.

### Text cells have NULL raw_value
This is correct! Text values use `raw_text` field (NUMERIC field can't store text).

## ✅ Success Checklist

- [ ] Python 3.10+ installed
- [ ] PostgreSQL running
- [ ] Virtual environment activated
- [ ] Dependencies installed
- [ ] `.env` configured
- [ ] Migrations applied (`alembic upgrade head`)
- [ ] First import successful
- [ ] Validation passes

## 📚 Next Steps

1. **Import Your Models**: Use `import` command with your Excel files
2. **Run Diagnostics**: Check for NULL values with `diagnose_nulls.py`
3. **Validate Integrity**: Run `validate_no_copying.py`
4. **Query Data**: Use psql or Python to explore imported data
5. **Read Architecture**: See [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) for details

## 💡 Pro Tips

- Always use `--validate` flag on first import
- Monitor `import.log` with `tail -f` during large imports
- Keep database backups before experimenting
- Text cells use `raw_text` and `calculated_text`, not `raw_value`
- The system never copies raw values - this is a critical integrity feature

---

**Need help?** Check [`README.md`](../README.md) or open an issue.