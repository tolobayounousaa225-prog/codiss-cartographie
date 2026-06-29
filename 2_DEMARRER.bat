@echo off
title CODISS - Serveur
color 0A

echo.
echo  === CODISS Cartographie - Demarrage du serveur ===
echo.
echo  Application  : ouvre le fichier index.html dans ton navigateur
echo  API Docs     : http://localhost:8000/api/docs
echo.
echo  ADMIN        : admin@codiss.ci / Admin@CODISS2024
echo  BRANCHE TEST : secretaire.abidjan@codiss.ci / Branch@2024
echo.
echo  Pour arreter : ferme cette fenetre
echo.

call venv\Scripts\activate.bat
uvicorn main_local:app --reload --port 8000 --host 0.0.0.0
