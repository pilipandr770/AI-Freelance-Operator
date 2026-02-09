@echo off
echo ========================================
echo AI Freelance Operator - Quick Start
echo ========================================
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
    echo.
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Check if .env exists
if not exist ".env" (
    echo.
    echo WARNING: .env file not found!
    echo Please copy .env.example to .env and configure it.
    echo.
    echo Copying .env.example to .env...
    copy .env.example .env
    echo.
    echo Please edit .env file with your credentials before continuing.
    pause
)

REM Install dependencies
echo.
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo ========================================
echo Starting AI Freelance Operator...
echo ========================================
echo.
python run.py

pause
