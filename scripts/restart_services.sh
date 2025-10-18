#!/bin/bash
# Restart all CapitalLens services to pick up code changes

echo "🔄 Restarting CapitalLens services..."
echo

# Kill any running Celery workers
echo "Stopping Celery workers..."
pkill -f "celery.*worker" || echo "  (no workers running)"

# Kill any running FastAPI servers
echo "Stopping FastAPI servers..."
pkill -f "uvicorn.*api.main" || echo "  (no servers running)"

# Kill any running Python processes for this project
echo "Stopping other Python processes..."
pkill -f "python.*excel_importer" || echo "  (none running)"

# Clear Python cache
echo
echo "Clearing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null
echo "  ✓ Cache cleared"

echo
echo "✅ All services stopped and cache cleared"
echo
echo "Next steps:"
echo "  1. Delete old model: python scripts/delete_model.py --model-id 5 --yes"
echo "  2. Re-import file: python scripts/excel_importer.py import --file <your_file> --name 'Model 1'"
echo "  3. Verify: python data_repair/diagnose_zero_calculated_values.py --model-id <new_id>"