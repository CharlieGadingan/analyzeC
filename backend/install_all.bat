@echo off
echo ========================================
echo CodeTracker Installation Script
echo ========================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed!
    echo Please download Python from https://python.org
    pause
    exit /b
)

:: Create virtual environment
echo 📦 Creating virtual environment...
if exist .venv (
    echo Virtual environment already exists, deleting old one...
    rmdir /s /q .venv
)
python -m venv .venv
echo ✅ Virtual environment created

:: Activate virtual environment
echo 🔧 Activating virtual environment...
call .venv\Scripts\activate

:: Upgrade pip
echo ⬆️ Upgrading pip...
python -m pip install --upgrade pip

:: Install all packages from requirements.txt
echo 📚 Installing packages...
pip install -r requirements.txt

echo.
echo ========================================
echo ✅ Installation Complete!
echo ========================================
echo.
echo To activate: .venv\Scripts\activate
echo To run app: python app.py
echo.
pause