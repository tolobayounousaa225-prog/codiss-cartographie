@echo off
title CODISS - Reset Base de Donnees
color 0C
echo Suppression de l'ancienne base...
if exist codiss_local.db del codiss_local.db
echo Recreer la base avec les bons mots de passe...
call venv\Scripts\activate.bat
python seed_db.py
echo.
echo Base recreee ! Lance 2_DEMARRER.bat puis connecte-toi.
pause
