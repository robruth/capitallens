#!/usr/bin/env node

/**
 * HyperFormula Wrapper for Python Integration
 * 
 * This Node.js script provides a subprocess interface for evaluating Excel formulas
 * using HyperFormula. It reads JSON input from stdin and outputs JSON results.
 * 
 * Usage:
 *   echo '{"sheets": [...], "queries": [...]}' | node hyperformula_wrapper.js
 * 
 * Input format:
 * {
 *   "sheets": [
 *     {
 *       "name": "Sheet1",
 *       "cells": [
 *         {"row": 0, "col": 0, "formula": "=SUM(B1:B10)"},
 *         {"row": 0, "col": 1, "value": 5}
 *       ]
 *     }
 *   ],
 *   "queries": [
 *     {"sheet": "Sheet1", "row": 0, "col": 0, "cell": "A1"}
 *   ]
 * }
 * 
 * Output format:
 * {
 *   "success": true,
 *   "results": [
 *     {"cell": "A1", "value": 50, "type": "number"}
 *   ]
 * }
 */

const { HyperFormula } = require('hyperformula');

// Configure stdin to read UTF-8
process.stdin.setEncoding('utf8');

let inputData = '';

// Read all input from stdin
process.stdin.on('data', (chunk) => {
    inputData += chunk;
});

// Process when all input is received
process.stdin.on('end', () => {
    try {
        // Parse input JSON
        const request = JSON.parse(inputData);
        
        // Validate request structure
        if (!request.sheets || !Array.isArray(request.sheets)) {
            throw new Error('Invalid request: missing or invalid "sheets" array');
        }
        if (!request.queries || !Array.isArray(request.queries)) {
            throw new Error('Invalid request: missing or invalid "queries" array');
        }
        
        // Initialize HyperFormula with GPL v3 license
        const hfOptions = {
            licenseKey: 'gpl-v3',
            // Enable more Excel-compatible functions
            useArrayArithmetic: true,
            useColumnIndex: false,
            // Precision settings
            precisionRounding: 10,
            precisionEpsilon: 1e-10,
            // Date settings for proper date handling
            nullDate: { year: 1899, month: 12, day: 30 },
            // Error handling
            smartRounding: true
        };
        
        const hf = HyperFormula.buildEmpty(hfOptions);
        
        // Add sheets and populate cells
        request.sheets.forEach(sheet => {
            if (!sheet.name) {
                throw new Error('Sheet missing "name" property');
            }
            
            // Add sheet to HyperFormula
            hf.addSheet(sheet.name);
            const sheetId = hf.getSheetId(sheet.name);
            
            if (sheetId === undefined) {
                throw new Error(`Failed to create sheet: ${sheet.name}`);
            }
            
            // Populate cells
            if (sheet.cells && Array.isArray(sheet.cells)) {
                sheet.cells.forEach(cell => {
                    const address = { sheet: sheetId, col: cell.col, row: cell.row };
                    
                    // Set cell content (formula or value)
                    if (cell.formula !== undefined) {
                        hf.setCellContents(address, [[cell.formula]]);
                    } else if (cell.value !== undefined) {
                        hf.setCellContents(address, [[cell.value]]);
                    }
                });
            }
        });
        
        // Execute queries and collect results
        const results = request.queries.map(query => {
            const sheetId = hf.getSheetId(query.sheet);
            
            if (sheetId === undefined) {
                return {
                    cell: query.cell,
                    value: null,
                    type: 'error',
                    error: `Sheet not found: ${query.sheet}`
                };
            }
            
            const address = { sheet: sheetId, col: query.col, row: query.row };
            
            try {
                const cellValue = hf.getCellValue(address);
                const cellType = hf.getCellType(address);
                
                // Handle different cell value types
                let resultValue = cellValue;
                let resultType = 'unknown';
                
                if (cellValue === null || cellValue === undefined) {
                    resultType = 'empty';
                    resultValue = null;
                } else if (typeof cellValue === 'number') {
                    resultType = 'number';
                    resultValue = cellValue;
                } else if (typeof cellValue === 'string') {
                    resultType = 'text';
                    resultValue = cellValue;
                } else if (typeof cellValue === 'boolean') {
                    resultType = 'boolean';
                    resultValue = cellValue;
                } else if (cellValue && cellValue.type === 'ERROR') {
                    resultType = 'error';
                    resultValue = cellValue.value || 'ERROR';
                }
                
                return {
                    cell: query.cell,
                    value: resultValue,
                    type: resultType,
                    cellType: cellType
                };
            } catch (error) {
                return {
                    cell: query.cell,
                    value: null,
                    type: 'error',
                    error: error.message
                };
            }
        });
        
        // Output success response
        const response = {
            success: true,
            results: results,
            stats: {
                sheets: request.sheets.length,
                queries: request.queries.length
            }
        };
        
        console.log(JSON.stringify(response));
        process.exit(0);
        
    } catch (error) {
        // Output error response
        const errorResponse = {
            success: false,
            error: error.message,
            stack: process.env.NODE_ENV === 'development' ? error.stack : undefined
        };
        
        console.log(JSON.stringify(errorResponse));
        process.exit(1);
    }
});

// Handle process errors
process.on('uncaughtException', (error) => {
    const errorResponse = {
        success: false,
        error: `Uncaught exception: ${error.message}`
    };
    console.log(JSON.stringify(errorResponse));
    process.exit(1);
});

process.on('unhandledRejection', (reason, promise) => {
    const errorResponse = {
        success: false,
        error: `Unhandled rejection: ${reason}`
    };
    console.log(JSON.stringify(errorResponse));
    process.exit(1);
});