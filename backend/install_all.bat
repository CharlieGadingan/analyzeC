@echo off
echo ========================================
echo CodeTracker Installation Script
echo ========================================
echo.

:: Navigate to backend folder
echo 📁 Navigating to backend folder...
cd backend
if errorlevel 1 (
    echo ❌ Backend folder not found!
    echo Please make sure you're in the correct directory
    pause
    exit /b
)
echo ✅ In: %CD%
echo.

:: Check if Python is installed
echo 🔍 Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed!
    echo.
    echo Please download Python from: https://python.org
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b
)
python --version
echo ✅ Python found
echo.

:: Create virtual environment
echo 📦 Creating virtual environment...
if exist .venv (
    echo Virtual environment already exists, deleting old one...
    rmdir /s /q .venv
)
python -m venv .venv
if errorlevel 1 (
    echo ❌ Failed to create virtual environment
    pause
    exit /b
)
echo ✅ Virtual environment created
echo.

:: Activate virtual environment
echo 🔧 Activating virtual environment...
call .venv\Scripts\activate
if errorlevel 1 (
    echo ❌ Failed to activate virtual environment
    pause
    exit /b
)
echo ✅ Virtual environment activated
echo.

:: Upgrade pip
echo ⬆️ Upgrading pip...
python -m pip install --upgrade pip
echo ✅ Pip upgraded
echo.

:: Check if requirements.txt exists
if not exist requirements.txt (
    echo 📝 Creating requirements.txt...
    (
        echo flask==2.3.3
        echo flask-cors==4.0.0
        echo firebase-admin==6.4.0
        echo gitpython==3.1.37
        echo gunicorn==21.2.0
        echo python-dotenv==1.0.0
    ) > requirements.txt
    echo ✅ requirements.txt created
    echo.
)

:: Install all packages from requirements.txt
echo 📚 Installing packages from requirements.txt...
echo This may take a few minutes...
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ Failed to install packages
    echo.
    echo Trying to install one by one...
    echo.
    pip install flask
    pip install flask-cors
    pip install firebase-admin
    pip install gitpython
    pip install gunicorn
    pip install python-dotenv
)
echo.

:: Show installed packages
echo ========================================
echo 📦 Installed Packages:
echo ========================================
pip list | findstr /i "flask firebase gitpython gunicorn"
echo.

:: Check Firebase credentials
echo ========================================
echo 🔐 Firebase Credentials Check:
echo ========================================
if exist serviceAccountKey.json (
    echo ✅ serviceAccountKey.json found
) else (
    echo ⚠️  serviceAccountKey.json NOT found!
    echo.
    echo To get Firebase credentials:
    echo 1. Go to https://console.firebase.google.com
    echo 2. Select your project: codetracker-406ac
    echo 3. Project Settings → Service Accounts
    echo 4. Click "Generate New Private Key"
    echo 5. Save the file as serviceAccountKey.json in the backend folder
)
echo.

echo ========================================
echo ✅ Installation Complete!
echo ========================================
echo.
echo 📝 Next Steps:
echo   1. Make sure serviceAccountKey.json is in the backend folder
echo   2. Run: python app.py
echo   3. Open browser to: http://localhost:5500
echo.
echo 📁 Current location: %CD%
echo.
pause