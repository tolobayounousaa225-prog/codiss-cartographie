$ErrorActionPreference = 'Continue'
Write-Host '=== RECHERCHE GIT ===' -ForegroundColor Cyan

$inPath = (Get-Command git -ErrorAction SilentlyContinue)
if ($inPath) {
    Write-Host "GIT DANS PATH: $($inPath.Source)" -ForegroundColor Green
    git --version
} else {
    Write-Host 'git NON dans PATH' -ForegroundColor Yellow
}

$ghGit = Get-ChildItem -Path "$env:LOCALAPPDATA\GitHubDesktop" -Recurse -Filter git.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ghGit) {
    Write-Host "GIT GITHUB DESKTOP: $($ghGit.FullName)" -ForegroundColor Green
    & $ghGit.FullName --version
} else {
    Write-Host 'GitHub Desktop git non trouve' -ForegroundColor Yellow
}

Write-Host ''
Write-Host '=== RESULTAT ===' -ForegroundColor Cyan
"" | Out-File "$PSScriptRoot\git_result.txt"
if ($inPath) {
    "GIT_PATH=$($inPath.Source)" | Out-File "$PSScriptRoot\git_result.txt"
} elseif ($ghGit) {
    "GIT_PATH=$($ghGit.FullName)" | Out-File "$PSScriptRoot\git_result.txt"
} else {
    "GIT_PATH=NONE" | Out-File "$PSScriptRoot\git_result.txt"
}

Write-Host 'Resultat sauvegarde dans git_result.txt' -ForegroundColor Green
Write-Host ''
Read-Host 'Appuyez sur Entree pour fermer'
