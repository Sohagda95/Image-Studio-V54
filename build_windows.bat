@echo off
setlocal
cd /d "%~dp0"
echo ================================================
echo Image Studio - Windows Build
echo ================================================
where py >nul 2>nul && set "PY=py" || set "PY=python"
%PY% -m pip install --upgrade pip
if errorlevel 1 goto :fail
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :fail
%PY% -m pip install pyinstaller
if errorlevel 1 goto :fail
%PY% -m compileall -q .
if errorlevel 1 goto :fail
%PY% -c "from production_v53 import self_test; r=self_test(); print(r); raise SystemExit(1 if r['summary']['failed'] else 0)"
if errorlevel 1 goto :fail
%PY% -c "import numpy, PIL, PySide6; import app; print("Dependency/import smoke test: PASS")"
if errorlevel 1 goto :fail
%PY% -m PyInstaller --noconfirm --clean ImageStudio.spec
if errorlevel 1 goto :fail
if exist "dist\ImageStudio" copy /y "launch_windows.bat" "dist\ImageStudio\launch_windows.bat" >nul
echo.
echo Build complete: dist\ImageStudio\ImageStudio.exe
echo License/activation: OFF
echo.
exit /b 0
:fail
echo.
echo Build failed. Review the error above.
exit /b 1
