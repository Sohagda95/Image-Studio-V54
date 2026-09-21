@echo off
setlocal
cd /d "%~dp0"
if exist "ImageStudio.exe" (
  start "Image Studio" "ImageStudio.exe"
) else (
  echo ImageStudio.exe was not found in this folder.
  echo Run build_windows.bat or use the PyInstaller dist\ImageStudio folder.
  pause
)
