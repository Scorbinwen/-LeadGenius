@echo off
REM Set Windows event loop policy before starting Python
REM This ensures Playwright can create subprocesses on Windows
set PYTHONUNBUFFERED=1
REM Script to start the backend server on Windows

echo Starting LeadGen AI Backend Server...
echo.


REM Install dependencies
echo Installing dependencies...
echo Upgrading pip first...
python -m pip install --upgrade pip --quiet
echo Installing project dependencies (this may take a few minutes)...
pip install -r requirements.txt --upgrade

REM Install Playwright browsers
echo Installing Playwright browsers...
playwright install chromium

REM Start the server using the wrapper script
REM This ensures Windows event loop policy is set correctly
echo.
echo Starting backend server on http://localhost:8000
echo API Documentation: http://localhost:8000/docs
echo.
echo Note: Using run_server.py to ensure proper Windows event loop configuration.
echo.
python run_server.py

pause

