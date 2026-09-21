@echo off
setlocal
cd /d "%~dp0"
echo ================================================
echo Image Studio V51 - Windows Setup
 echo ================================================
where py >nul 2>nul && set PY=py || set PY=python
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :fail
%PY% -m pip install pyinstaller
if errorlevel 1 goto :fail
%PY% -c "import numpy, PIL, PySide6; import app; print("Dependency/import smoke test: PASS")"
if errorlevel 1 goto :fail
%PY% -m PyInstaller --noconfirm --clean ImageStudio.spec
if errorlevel 1 goto :fail
mkdir "%~dp0portable_data" 2>nul
copy /y "%~dp0launch_windows.bat" "%~dp0dist\launch_windows.bat" >nul
 echo.
echo Setup/build complete: dist\ImageStudio\ImageStudio.exe
pause
exit /b 0
:fail
echo Setup failed. Review the error above.
pause
exit /b 1
