# NumPy startup error

If Windows shows `ModuleNotFoundError: No module named 'numpy'`, the EXE was built without NumPy.

This release fixes that by:
- adding `numpy>=1.26` to `requirements.txt`;
- running an import smoke test before PyInstaller;
- building from `ImageStudio.spec`;
- explicitly including NumPy as a PyInstaller hidden import.

Re-run the GitHub Actions workflow after replacing the repository files with this release. Do not reuse the old `dist` artifact.

## Fixed build note

The previous GitHub build could fail during the application import smoke test because `app.py` imported Pillow classes (`ImageFilter`, `ImageEnhance`, `ImageOps`, `ImageDraw`, `ImageChops`) from `ai_backends.py`, although those classes belong to Pillow.

This release fixes that import boundary:
- Pillow image helpers are imported directly from `PIL` in `app.py`.
- `ai_backends.py` contains only the optional `rembg` backend helpers.
- NumPy remains a required dependency because several production modules use it.

The GitHub workflow now stops before PyInstaller if the application import smoke test fails.
