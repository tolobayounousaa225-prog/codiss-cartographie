$ErrorActionPreference = 'Continue'
$GIT = "C:\Users\TOLOBA\AppData\Local\GitHubDesktop\app-3.5.6\resources\app\git\cmd\git.exe"
$REPO_DIR = "C:\Users\TOLOBA\OneDrive\Bureau\CODISS_API"

Set-Location $REPO_DIR

Write-Host '================================================' -ForegroundColor Cyan
Write-Host '   CODISS - Deploiement Git' -ForegroundColor Cyan
Write-Host '================================================' -ForegroundColor Cyan
Write-Host ''

# Trouver le nom utilisateur GitHub depuis la config GitHub Desktop
$ghConfig = "$env:APPDATA\GitHub Desktop\config.json"
$ghUser = ""
if (Test-Path $ghConfig) {
    $config = Get-Content $ghConfig -Raw | ConvertFrom-Json
    $ghUser = $config.login
    Write-Host "Utilisateur GitHub detecte: $ghUser" -ForegroundColor Green
} else {
    Write-Host "Config GitHub Desktop non trouvee. Recherche alternative..." -ForegroundColor Yellow
    # Essayer gitconfig global
    $gitconfigPath = "$env:USERPROFILE\.gitconfig"
    if (Test-Path $gitconfigPath) {
        $gitconfig = Get-Content $gitconfigPath
        $nameLine = $gitconfig | Where-Object { $_ -match 'name\s*=' } | Select-Object -First 1
        Write-Host "gitconfig: $nameLine" -ForegroundColor Yellow
    }
}

# Configurer git identity si pas configurée
& $GIT config --global user.email "tolobayounousaa225@gmail.com" 2>$null
& $GIT config --global user.name "TOLOBA" 2>$null
Write-Host "Identity git configuree" -ForegroundColor Green

# Initialiser le depot git
Write-Host ''
Write-Host 'ETAPE 1: Initialisation Git...' -ForegroundColor Yellow
if (Test-Path ".git") {
    Write-Host "Depot git existant, mise a jour..." -ForegroundColor Cyan
    & $GIT remote remove origin 2>$null
} else {
    & $GIT init
    Write-Host "Depot git cree" -ForegroundColor Green
}

# Ajouter tous les fichiers
Write-Host ''
Write-Host 'ETAPE 2: Ajout des fichiers...' -ForegroundColor Yellow
& $GIT add .
Write-Host "Fichiers ajoutes" -ForegroundColor Green

# Commit
Write-Host ''
Write-Host 'ETAPE 3: Commit...' -ForegroundColor Yellow
& $GIT commit -m "CODISS Cartographie - Deploiement initial"
Write-Host "Commit cree" -ForegroundColor Green

# Branch main
Write-Host ''
Write-Host 'ETAPE 4: Branche main...' -ForegroundColor Yellow
& $GIT branch -M main
Write-Host "Branche main creee" -ForegroundColor Green

# Sauvegarder le statut
$status = & $GIT log --oneline -1
"GIT_STATUS=OK" | Out-File "$REPO_DIR\deploy_result.txt"
"LAST_COMMIT=$status" | Add-Content "$REPO_DIR\deploy_result.txt"
"GH_USER=$ghUser" | Add-Content "$REPO_DIR\deploy_result.txt"

Write-Host ''
Write-Host '================================================' -ForegroundColor Green
Write-Host '   GIT INIT + COMMIT REUSSI !' -ForegroundColor Green
Write-Host '================================================' -ForegroundColor Green
Write-Host ''
Write-Host "Dernier commit: $status" -ForegroundColor Cyan
Write-Host ''

if ($ghUser -ne "") {
    Write-Host "Prochaine etape: pousser vers GitHub" -ForegroundColor Yellow
    Write-Host "URL: https://github.com/$ghUser/codiss-cartographie.git" -ForegroundColor Yellow
    "REPO_URL=https://github.com/$ghUser/codiss-cartographie.git" | Add-Content "$REPO_DIR\deploy_result.txt"
} else {
    Write-Host "IMPORTANT: Renseigne ton nom d'utilisateur GitHub dans deploy_result.txt" -ForegroundColor Red
}

Write-Host ''
Read-Host 'Appuyez sur Entree pour fermer'
