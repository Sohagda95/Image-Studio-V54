# V51 — Windows Production Build & Installation

Adds a deployment and installation layer for the desktop application.

## Features
- Windows setup/build script using PyInstaller
- Portable launcher
- Installation/data-directory initialization
- Environment and dependency diagnostics
- Writable-directory verification
- Installation manifest
- V51 GUI diagnostics tab
- Existing V7–V50 modules retained

## Important
PyInstaller packages the Python application and its declared/runtime dependencies. Optional AI/OCR/GPU packages remain optional and are reported by diagnostics. Actual GPU acceleration is not claimed unless a processing backend uses it.
