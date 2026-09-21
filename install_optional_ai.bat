@echo off
echo Installing optional AI background-removal backend...
python -m pip install rembg onnxruntime
echo.
echo Optional AI backend installed. Restart Image Studio.
pause
