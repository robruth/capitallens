# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed - 2025-01-18

#### CLI Consolidation: Dual-Mode Support

**Summary:**
Consolidated duplicate CLI scripts into a single dual-mode implementation that supports both direct database access and FastAPI backend integration.

**Changes:**
- **Merged** `excel_importer_cli.py` functionality into `excel_importer.py`
- **Added** `--api-url` flag to enable API mode
- **Preserved** backward compatibility - direct mode works exactly as before
- **Updated** test suite to import from service modules
- **Updated** all documentation to reflect dual-mode usage

**Migration Guide:**

For users previously using `excel_importer_cli.py`:
```bash
# OLD (still works but deprecated)
python scripts/excel_importer_cli.py import --file model.xlsx --name "Model" --api-url http://localhost:8000

# NEW (recommended)
python scripts/excel_importer.py import --file model.xlsx --name "Model" --api-url http://localhost:8000
```

For existing users of `excel_importer.py`:
- No changes required! Direct mode works exactly as before
- Optionally add `--api-url` flag to use API mode

**Files Modified:**
- `scripts/excel_importer.py` - Now supports both modes
- `scripts/excel_importer_legacy.py` - Backup of original (for reference)
- `tests/test_importer.py` - Updated to import from services
- `README.md` - Added dual-mode examples
- `docs/QUICKSTART.md` - Updated with both modes
- `docs/LOCAL_DEVELOPMENT.md` - Updated CLI examples
- `docs/ARCHITECTURE.md` - Updated file structure

**Benefits:**
- ✅ Single CLI script (no confusion)
- ✅ Backward compatible (existing scripts work unchanged)
- ✅ API mode support (when FastAPI backend is available)
- ✅ Consistent documentation
- ✅ Easier maintenance

**Breaking Changes:**
- None - fully backward compatible

**Deprecation Notice:**
- `excel_importer_cli.py` is now deprecated and will be removed in a future release
- Use `excel_importer.py` with `--api-url` flag instead

---

## [1.0.0] - 2024-12

### Added
- Initial release with Excel parsing and PostgreSQL import
- Formula evaluation with multiple engines
- Circular reference detection and solving
- Comprehensive validation and testing suite
- Database migrations with Alembic
- Documentation and quickstart guides