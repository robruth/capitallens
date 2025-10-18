# Formula Evaluation Architecture - Visual Guide

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Excel Import Service                                 │
│                    (services/excel_import_service.py)                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
        ┌────────────────────┐          ┌────────────────────┐
        │  Formula Parser    │          │   HyperFormula     │
        │  (formula_service) │          │   Evaluator        │
        └────────────────────┘          └────────────────────┘
                    │                               │
                    │                               ▼
                    │                   ┌────────────────────┐
                    │                   │   Node.js Wrapper  │
                    │                   │  (hyperformula_    │
                    │                   │   wrapper.js)      │
                    │                   └────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                        ┌────────────────────┐
                        │  HyperFormula      │
                        │  (NPM Package)     │
                        └────────────────────┘
```

## Data Flow Diagram

```
┌──────────────┐
│ Excel File   │
│ (.xlsx)      │
└──────┬───────┘
       │
       │ openpyxl.load_workbook()
       ▼
┌──────────────────────────────────────────────────────┐
│ Parsed Workbook Data                                 │
│ ┌──────────────┐  ┌──────────────┐                  │
│ │ Sheet1       │  │ Sheet2       │                  │
│ │ - A1: =B1+1  │  │ - A1: 100    │                  │
│ │ - B1: 10     │  │ - A2: =A1*2  │                  │
│ │ - C1: =A1*2  │  └──────────────┘                  │
│ └──────────────┘                                     │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ _build_hyperformula_sheets()
                       ▼
┌──────────────────────────────────────────────────────┐
│ HyperFormula Data Structure                          │
│ {                                                    │
│   "sheets": [                                        │
│     {                                                │
│       "name": "Sheet1",                              │
│       "cells": [                                     │
│         {"row": 0, "col": 0, "formula": "=B1+1"},   │
│         {"row": 0, "col": 1, "value": 10},          │
│         {"row": 0, "col": 2, "formula": "=A1*2"}    │
│       ]                                              │
│     },                                               │
│     {                                                │
│       "name": "Sheet2",                              │
│       "cells": [...]                                 │
│     }                                                │
│   ]                                                  │
│ }                                                    │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ Topological Sort
                       ▼
┌──────────────────────────────────────────────────────┐
│ Evaluation Batches (Dependency Order)                │
│ ┌─────────────────────────────────────────┐         │
│ │ Batch 0: [B1(Sheet1), A1(Sheet2)]       │         │
│ │          (no dependencies)               │         │
│ └─────────────────────────────────────────┘         │
│ ┌─────────────────────────────────────────┐         │
│ │ Batch 1: [A1(Sheet1), A2(Sheet2)]       │         │
│ │          (depends on Batch 0)            │         │
│ └─────────────────────────────────────────┘         │
│ ┌─────────────────────────────────────────┐         │
│ │ Batch 2: [C1(Sheet1)]                   │         │
│ │          (depends on Batches 0 & 1)      │         │
│ └─────────────────────────────────────────┘         │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ For each batch
                       ▼
┌──────────────────────────────────────────────────────┐
│ _batch_evaluate_hyperformula()                       │
│                                                      │
│ Build queries for batch:                            │
│ [                                                    │
│   {"sheet": "Sheet1", "row": 0, "col": 1, ...},    │
│   {"sheet": "Sheet2", "row": 0, "col": 0, ...}     │
│ ]                                                    │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ hf_evaluator.evaluate_batch()
                       ▼
┌──────────────────────────────────────────────────────┐
│ Subprocess Call to Node.js                           │
│                                                      │
│ stdin  ─────────▶  hyperformula_wrapper.js          │
│                                                      │
│ stdout ◀─────────  { "success": true, ...}          │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ Evaluation Results                                   │
│ {                                                    │
│   "success": true,                                   │
│   "results": [                                       │
│     {"cell": "Sheet1!B1", "value": 10, "type": ...},│
│     {"cell": "Sheet1!A1", "value": 11, "type": ...},│
│     {"cell": "Sheet1!C1", "value": 22, "type": ...} │
│   ]                                                  │
│ }                                                    │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ Store in cache
                       ▼
┌──────────────────────────────────────────────────────┐
│ Evaluation Cache                                     │
│ {                                                    │
│   "Sheet1!A1": 11.0,                                │
│   "Sheet1!B1": 10.0,                                │
│   "Sheet1!C1": 22.0,                                │
│   ...                                                │
│ }                                                    │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ Compare with raw_value
                       ▼
┌──────────────────────────────────────────────────────┐
│ Cell Data with Results                               │
│ {                                                    │
│   "sheet_name": "Sheet1",                           │
│   "cell": "A1",                                     │
│   "formula": "=B1+1",                               │
│   "raw_value": 11.0,         ← From Excel           │
│   "calculated_value": 11.0,  ← From HyperFormula   │
│   "has_mismatch": false      ← Validation           │
│ }                                                    │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
                ┌──────────────┐
                │  Database    │
                │  (Cell table)│
                └──────────────┘
```

## Circular Reference Evaluation Flow

```
┌──────────────────────────────────────────────────────┐
│ Circular Cells Detected                              │
│ - A1 = B1 + 1                                       │
│ - B1 = A1 / 2                                       │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ Initialize with zeros
                       ▼
┌──────────────────────────────────────────────────────┐
│ Iteration 0                                          │
│ Values: {A1: 0.0, B1: 0.0}                          │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ Update HyperFormula sheets
                       │ with current values
                       ▼
┌──────────────────────────────────────────────────────┐
│ HyperFormula Evaluation (Iteration 1)                │
│                                                      │
│ Input sheets with A1=0, B1=0                        │
│ Evaluate: A1 = B1 + 1 = 0 + 1 = 1                  │
│          B1 = A1 / 2 = 0 / 2 = 0                   │
│                                                      │
│ Results: {A1: 1.0, B1: 0.0}                         │
│ Max Change: 1.0                                      │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ Check convergence (no)
                       ▼
┌──────────────────────────────────────────────────────┐
│ Iteration 2                                          │
│                                                      │
│ Input sheets with A1=1, B1=0                        │
│ Evaluate: A1 = B1 + 1 = 0 + 1 = 1                  │
│          B1 = A1 / 2 = 1 / 2 = 0.5                 │
│                                                      │
│ Results: {A1: 1.0, B1: 0.5}                         │
│ Max Change: 0.5                                      │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ Continue iterating...
                       ▼
┌──────────────────────────────────────────────────────┐
│ Iteration N (Converged)                              │
│                                                      │
│ Results: {A1: 2.0, B1: 1.0}                         │
│ Max Change: < 1e-6 (threshold)                      │
│                                                      │
│ ✓ Converged!                                         │
└──────────────────────┬───────────────────────────────┘
                       │
                       │ Apply results to cells
                       ▼
                 ┌──────────────┐
                 │  Database    │
                 └──────────────┘
```

## Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                      ExcelImportService                              │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ evaluate_formulas(cells_data)                              │    │
│  │                                                             │    │
│  │  1. Build HyperFormula sheets ──────────────┐             │    │
│  │     (_build_hyperformula_sheets)            │             │    │
│  │                                              │             │    │
│  │  2. Topological sort ────────────────────┐  │             │    │
│  │     (_topological_sort_formulas)         │  │             │    │
│  │                                           │  │             │    │
│  │  3. For each batch:                      │  │             │    │
│  │     ┌─────────────────────────────────┐  │  │             │    │
│  │     │ _evaluate_batch()               │  │  │             │    │
│  │     │   ↓                              │  │  │             │    │
│  │     │ _batch_evaluate_hyperformula()  │  │  │             │    │
│  │     │   ↓                              │  │  │             │    │
│  │     │ _evaluate_numeric_formula() ────┼──┼──┼──────┐     │    │
│  │     │   (for each cell in batch)      │  │  │      │     │    │
│  │     └─────────────────────────────────┘  │  │      │     │    │
│  │                                           │  │      │     │    │
│  │  4. Circular references:                 │  │      │     │    │
│  │     _evaluate_circular_cells_hf() ───────┼──┼──────┤     │    │
│  │                                           │  │      │     │    │
│  └───────────────────────────────────────────┼──┼──────┼─────┘    │
│                                              │  │      │          │
└──────────────────────────────────────────────┼──┼──────┼──────────┘
                                               │  │      │
         ┌─────────────────────────────────────┘  │      │
         │  ┌────────────────────────────────────┘      │
         │  │  ┌─────────────────────────────────────────┘
         ▼  ▼  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FormulaParser                                   │
│                                                                      │
│  cell_to_coordinates("A1")     → (0, 0)                             │
│  coordinates_to_cell(0, 0)     → "A1"                               │
│  parse_range("A1:B10")         → ((0,0), (9,1))                     │
│  extract_dependencies(formula) → ["Sheet1!A1", ...]                 │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
┌──────────────────────┐  ┌──────────────────────┐
│ CircularReference    │  │  HyperFormula        │
│ Detector             │  │  Evaluator           │
│                      │  │                      │
│ - add_dependency()   │  │ evaluate_batch()     │
│ - detect_cycles()    │  │     ↓                │
│ - is_circular()      │  │  subprocess.Popen()  │
└──────────────────────┘  └──────┬───────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  hyperformula_wrapper.js│
                    │                         │
                    │  - Reads JSON from stdin│
                    │  - Builds HF instance   │
                    │  - Evaluates queries    │
                    │  - Returns JSON results │
                    └─────────────────────────┘
```

## Cell Reference Conversion Examples

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Cell Address Conversions                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Excel Format        Zero-Based Coordinates      Description        │
│  ────────────        ───────────────────────     ───────────        │
│                                                                      │
│  A1            →     (row: 0, col: 0)            First cell         │
│  B1            →     (row: 0, col: 1)            Second column      │
│  A2            →     (row: 1, col: 0)            Second row         │
│  Z1            →     (row: 0, col: 25)           26th column        │
│  AA1           →     (row: 0, col: 26)           27th column        │
│  AB1           →     (row: 0, col: 27)           28th column        │
│  BA1           →     (row: 0, col: 52)           53rd column        │
│                                                                      │
│  Sheet1!A1     →     {sheet: "Sheet1", row: 0, col: 0}             │
│  Sheet2!AA100  →     {sheet: "Sheet2", row: 99, col: 26}           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                   Range Reference Parsing                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Excel Range         Parsed Coordinates                             │
│  ────────────        ──────────────────────────────────             │
│                                                                      │
│  A1:B10        →     start: (0, 0), end: (9, 1)                    │
│                      (10 rows × 2 columns = 20 cells)               │
│                                                                      │
│  C5:C5         →     start: (4, 2), end: (4, 2)                    │
│                      (1 cell - single cell range)                   │
│                                                                      │
│  A1:Z100       →     start: (0, 0), end: (99, 25)                  │
│                      (100 rows × 26 columns = 2,600 cells)          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Error Handling Flow

```
                    Formula Evaluation
                            │
                            ▼
                ┌───────────────────────┐
                │ HyperFormula Execute  │
                └───────────┬───────────┘
                            │
                ┌───────────┴────────────┐
                │                        │
         Success │                       │ Error
                │                        │
                ▼                        ▼
    ┌──────────────────┐    ┌──────────────────────┐
    │ Result Type?     │    │ Evaluation Failed?   │
    └─────────┬────────┘    └──────────┬───────────┘
              │                        │
    ┌─────────┼────────────┐           │
    │         │            │           │
    ▼         ▼            ▼           ▼
┌────────┐ ┌──────┐  ┌────────┐  ┌──────────┐
│Number  │ │Error │  │Empty   │  │Process   │
│        │ │      │  │        │  │Error     │
└───┬────┘ └───┬──┘  └───┬────┘  └────┬─────┘
    │          │         │            │
    │          │         │            │
    ▼          ▼         ▼            ▼
┌──────────────────────────────────────────┐
│ Result Processing                        │
├──────────────────────────────────────────┤
│                                          │
│ Number:  calculated_value = result      │
│          Compare with raw_value          │
│                                          │
│ Error:   calculated_value = NULL        │
│          Log error type (#DIV/0!, etc)  │
│          stats['errors'] += 1            │
│                                          │
│ Empty:   calculated_value = NULL        │
│          (cell has no value)             │
│                                          │
│ Failed:  calculated_value = NULL        │
│          Log evaluation failure          │
│          stats['errors'] += 1            │
│                                          │
└──────────────────────────────────────────┘
```

## Cache Management Strategy

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Evaluation Cache                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Lifecycle:                                                          │
│  1. Initialize empty dict at start of evaluate_formulas()           │
│  2. Populate during batch evaluation                                │
│  3. Reuse for cells referenced multiple times                       │
│  4. Pass to circular solver for iterative evaluation                │
│  5. Clear after import completes                                    │
│                                                                      │
│  Structure:                                                          │
│  {                                                                   │
│    "Sheet1!A1": 100.0,      # Simple value                          │
│    "Sheet1!B1": 200.0,      # Formula result                        │
│    "Sheet2!A1": 50.0,       # Cross-sheet reference                 │
│    ...                                                               │
│  }                                                                   │
│                                                                      │
│  Benefits:                                                           │
│  ✓ Avoid re-evaluating same cell multiple times                     │
│  ✓ Speed up cells with common dependencies                          │
│  ✓ Accelerate circular reference convergence                        │
│  ✓ Reduce HyperFormula subprocess calls                             │
│                                                                      │
│  Memory Impact:                                                      │
│  - Typical cell: ~50 bytes (reference + float)                      │
│  - 10,000 cells: ~500 KB                                            │
│  - 100,000 cells: ~5 MB                                             │
│  → Negligible for modern systems                                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Implementation Phases

```
Phase 1: Utilities          Phase 2: Batch Eval       Phase 3: Main Flow
└─────────────┬─────────    └───────────┬─────────    └──────────┬──────────
              │                         │                        │
              ▼                         ▼                        ▼
    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
    │ FormulaParser    │    │ _batch_evaluate  │    │ evaluate_formulas│
    │ - cell_to_coords │    │ - Build queries  │    │ - Use batching   │
    │ - coords_to_cell │    │ - Call HF        │    │ - Topo sort      │
    │ - parse_range    │    │ - Cache results  │    │ - Progress track │
    └──────────────────┘    └──────────────────┘    └──────────────────┘
              │                         │                        │
              ▼                         ▼                        ▼
    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
    │ _topological_sort│    │ _evaluate_numeric│    │ Full integration │
    │ - Kahn algorithm │    │ - Replace raw_val│    │ - All formulas   │
    │ - Batching       │    │ - Use HF         │    │ - Real eval      │
    └──────────────────┘    └──────────────────┘    └──────────────────┘
              │                         │                        │
              ▼                         ▼                        ▼
    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
    │ _build_hf_sheets │    │ Integration tests│    │ System tests     │
    │ - Convert format │    │ - Simple formulas│    │ - Real workbooks │
    │ - All sheets     │    │ - Verify results │    │ - Validation     │
    └──────────────────┘    └──────────────────┘    └──────────────────┘
              │                         │                        │
              ▼                         ▼                        ▼
         Unit Tests              Integration Tests         Acceptance Tests

Phase 4: Circular Refs     Phase 5: Cleanup
└───────────┬───────────    └──────────┬────────
            │                          │
            ▼                          ▼
┌──────────────────────┐    ┌──────────────────────┐
│ _eval_circular_hf    │    │ Remove placeholders  │
│ - Iterative eval     │    │ Update docs          │
│ - HF per iteration   │    │ Final validation     │
└──────────────────────┘    └──────────────────────┘
            │                          │
            ▼                          ▼
┌──────────────────────┐    ┌──────────────────────┐
│ Convergence tests    │    │ Production ready     │
│ - Complex cycles     │    │ ✓ All tests pass     │
│ - Edge cases         │    │ ✓ No raw_value copy  │
└──────────────────────┘    └──────────────────────┘
```

## Key Design Decisions Summary

| Decision | Rationale |
|----------|-----------|
| **HyperFormula for all** | Maximize accuracy and Excel compatibility |
| **Topological sorting** | Evaluate dependencies before dependents |
| **Batch evaluation** | Reduce subprocess overhead |
| **Evaluation cache** | Avoid redundant calculations |
| **NULL on error** | Never copy raw_value, maintain data integrity |
| **Keep sheets in memory** | Typical workbooks fit easily |
| **Iterative HF for circular** | Ensure accurate convergence |
| **Progress tracking** | User experience for long imports |

## Success Metrics

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Success Criteria                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Functional:                                                         │
│  ✓ 100% formulas evaluated through HyperFormula                     │
│  ✓ 0% raw_value copying violations                                  │
│  ✓ Range references (A1:B10) supported                              │
│  ✓ Cross-sheet references supported                                 │
│  ✓ Topological evaluation order                                     │
│  ✓ Circular references converge                                     │
│  ✓ Excel errors handled (#DIV/0!, #REF!, etc)                      │
│  ✓ Results cached and reused                                        │
│                                                                      │
│  Performance:                                                        │
│  ✓ Import time < 1.5x baseline                                      │
│  ✓ Memory usage < 2x baseline                                       │
│  ✓ 99% circular convergence < 100 iterations                        │
│                                                                      │
│  Quality:                                                            │
│  ✓ All existing tests pass                                          │
│  ✓ > 90% code coverage                                              │
│  ✓ < 1% error rate on real workbooks                                │
│  ✓ No data integrity violations                                     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘