# V44 Smart Production Workflow

Adds a deterministic local workflow orchestrator with a single Run action:
1. Preflight source artwork
2. Conservative cleanup
3. Print-ready size/DPI preparation
4. QC re-check
5. Production package ZIP + manifest

The workflow is an automation layer around local raster preparation. It does **not** claim calibrated ICC/RIP output, press calibration, generative AI reconstruction, or automatic perfect color separation.
