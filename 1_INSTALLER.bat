@echo off
title CODISS Installation
color 0A

echo.
echo  === CODISS Cartographie - Installation ===
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERREUR: Python n'est pas installe !
    pause
    exit /b 1
)
echo OK: Python detecte.

if exist "venv" (
    echo Suppression ancien environnement...
    rmdir /s /q venv
)

echo Creation de l'environnement virtuel...
python -m venv venv
echo OK: Environnement virtuel cree.

echo Activation...
call venv\Scripts\activate.bat

echo Mise a jour pip...
python -m pip install --upgrade pip -q

echo Installation des dependances (peut prendre 3-5 minutes)...
pip install fastapi uvicorn[standard] sqlalchemy aiosqlite "python-jose[cryptography]" "passlib[bcrypt]" python-multipart

if %errorlevel% neq 0 (
    echo ERREUR lors de l'installation.
    pause
    exit /b 1
)
echo OK: Dependances installees.

echo Initialisation de la base de donnees...
python seed_db.py

if %errorlevel% neq 0 (
    echo ERREUR lors de l'initialisation de la base.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo  Installation terminee avec succes !
echo  Lance maintenant : 2_DEMARRER.bat
echo ==========================================
echo.
pause
