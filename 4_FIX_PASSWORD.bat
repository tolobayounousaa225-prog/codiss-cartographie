@echo off
title CODISS - Fix Password
color 0A
echo Correction des mots de passe...
call venv\Scripts\activate.bat
python fix_password.py
