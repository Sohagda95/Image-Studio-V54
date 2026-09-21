# Image Studio — GitHub Windows Build

This repository is prepared for building the Image Studio desktop app on GitHub Actions or locally on Windows.

## License system

**License/activation is OFF in this release.** No key, activation server, or license file is required. The V53 Profile & Workspace area only manages profile and workspace bundles.

## GitHub Actions build

1. Create a GitHub repository.
2. Upload/extract the contents of this folder into the repository root.
3. Commit and push.
4. Open **Actions → Build Windows EXE → Run workflow**.
5. Download the `ImageStudio-Windows` artifact from the completed workflow.

A Windows build also runs `compileall`, the V53 core self-test, and a dependency/app import smoke test before packaging. NumPy is a mandatory runtime dependency because several production modules import it at application startup.

## Tagged builds

Pushing a tag such as `v54.0.0` also triggers the workflow.

## Local Windows build

```bat
build_windows.bat
```

The resulting PyInstaller application is placed under `dist\ImageStudio\`.

## Optional AI backend

The base build does not require optional AI packages. If you want the optional `rembg` backend, run:

```bat
install_optional_ai.bat
```

Then rebuild the application.

## Data

Application data is stored outside the repository. The app creates its local data directories as needed. Do not commit customer artwork, job databases, backups, or generated production files to Git.


### V54 FIXED V3
This build includes a static UI-contract check that catches missing Qt slot/method definitions before PyInstaller runs. The Batch Production Queue now defines `apply_selected_preset`, which was previously referenced by a signal connection without a method implementation. License/activation remains disabled.
