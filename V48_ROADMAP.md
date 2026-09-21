# V48 Roadmap — Full System Validation & Test Center

## Added
- Deterministic validation runner for the production modules.
- Optional dependency detection for rembg, OpenCV, OCR and PySide6.
- Image create/load/process/resize/alpha/PNG integrity checks.
- V42→V47 SQLite integration smoke test.
- V41 project snapshot/archive integrity test.
- PASS / WARNING / FAIL report with JSON export.
- Desktop validation tab with test table and diagnostic export.

## Important scope
- V48 validates software/data-path integrity; it does not replace press calibration, ICC/RIP certification, physical film exposure tests, or real-world garment testing.
- Optional backends remain explicitly reported as warnings when unavailable.
