@echo off
chcp 65001 >nul
title CODISS - Déploiement sur GitHub + Render
color 0A
cls

echo ╔══════════════════════════════════════════════════╗
echo ║   CODISS - DÉPLOIEMENT EN LIGNE (Render.com)     ║
echo ╚══════════════════════════════════════════════════╝
echo.

REM === Aller dans le dossier CODISS ===
cd /d "%~dp0"
echo 📁 Dossier : %CD%
echo.

REM === Vérifier si Git est disponible ===
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Git n'est pas installé !
    echo.
    echo Télécharge Git sur : https://git-scm.com/download/win
    echo Installe-le, puis relance ce script.
    start https://git-scm.com/download/win
    pause
    exit /b 1
)
echo ✅ Git détecté :
git --version
echo.

REM === Ouvrir GitHub pour trouver le nom d'utilisateur ===
echo 🌐 Ouverture de GitHub...
echo.
echo ⚠️  IMPORTANT : Dans la page GitHub qui va s'ouvrir,
echo    Regarde en haut à droite - tu veras ton nom d'utilisateur
echo    (ex: github.com/TON_NOM)
echo.
start "" "https://github.com"
echo.
timeout /t 3 /nobreak >nul

REM === Saisir le nom d'utilisateur GitHub ===
:saisir_username
echo ──────────────────────────────────────────────────
set /p GITHUB_USER=👤 Entre ton nom d'utilisateur GitHub (ex: jean-dupont) :
echo ──────────────────────────────────────────────────
echo.

if "%GITHUB_USER%"=="" (
    echo ❌ Le nom d'utilisateur ne peut pas être vide.
    goto saisir_username
)

set REPO_NAME=codiss-cartographie
set REPO_URL=https://github.com/%GITHUB_USER%/%REPO_NAME%.git

echo 🔗 URL du dépôt : %REPO_URL%
echo.

REM === Créer le dépôt GitHub ===
echo 📋 ÉTAPE 1/4 : Création du dépôt GitHub
echo.
echo ⚠️  Suis ces étapes dans le navigateur :
echo    1. Clique sur + New repository (ou va sur https://github.com/new)
echo    2. Repository name : codiss-cartographie
echo    3. Laisse en PUBLIC
echo    4. NE coche PAS Initialize this repository
echo    5. Clique Create repository
echo.
start "" "https://github.com/new"
echo.
pause

REM === Initialiser Git ===
echo 📋 ÉTAPE 2/4 : Initialisation Git...
echo.

if exist ".git" (
    echo ℹ️  Dépôt git déjà initialisé - mise à jour...
    git remote remove origin 2>nul
) else (
    git init
    echo ✅ Dépôt git créé
)

REM === Créer .gitignore si absent ===
if not exist ".gitignore" (
    echo __pycache__/ > .gitignore
    echo *.pyc >> .gitignore
    echo venv/ >> .gitignore
    echo .env >> .gitignore
    echo *.db >> .gitignore
    echo *.sqlite >> .gitignore
)

REM === Ajouter tous les fichiers ===
git add .
echo ✅ Fichiers ajoutés

REM === Créer le commit ===
git commit -m "CODISS Cartographie - Déploiement initial"
echo ✅ Commit créé
echo.

REM === Lier au dépôt GitHub ===
echo 📋 ÉTAPE 3/4 : Connexion à GitHub...
git branch -M main
git remote add origin %REPO_URL%
echo ✅ Dépôt GitHub lié : %REPO_URL%
echo.

REM === Pousser le code ===
echo 📋 ÉTAPE 4/4 : Envoi du code sur GitHub...
echo (Une fenêtre de connexion GitHub peut apparaître - connecte-toi)
echo.
git push -u origin main

if %errorlevel% neq 0 (
    echo.
    echo ❌ Erreur lors de l'envoi. Essaie ces solutions :
    echo    1. Vérifie que le dépôt "%REPO_NAME%" existe sur GitHub
    echo    2. Vérifie ton nom d'utilisateur : %GITHUB_USER%
    echo    3. Connecte-toi à GitHub si une fenêtre s'est ouverte
    pause
    exit /b 1
)

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║   ✅ CODE ENVOYÉ SUR GITHUB AVEC SUCCÈS !        ║
echo ╚══════════════════════════════════════════════════╝
echo.
echo 🚀 DERNIÈRE ÉTAPE : Déployer sur Render.com
echo.
echo    1. Va sur https://render.com
echo    2. Crée un compte GRATUIT avec ton compte GitHub
echo    3. Clique + New → Web Service
echo    4. Sélectionne : %GITHUB_USER%/%REPO_NAME%
echo    5. Build Command : pip install -r requirements_render.txt
echo    6. Start Command : uvicorn main_local:app --host 0.0.0.0 --port $PORT
echo    7. Instance Type : FREE
echo    8. Clique Create Web Service
echo.
echo 🌐 Ouverture de Render.com...
start "" "https://render.com"
echo.
echo Ton app sera en ligne à :
echo https://%REPO_NAME%.onrender.com
echo.
pause
