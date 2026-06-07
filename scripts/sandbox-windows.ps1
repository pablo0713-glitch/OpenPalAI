param(
    [ValidateSet("up", "check")]
    [string]$Command = "up",
    [int]$Port = 18080
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Sandbox = Join-Path $Root ".sandbox\windows"
$DataDir = Join-Path $Sandbox "data"
$EnvFile = Join-Path $Sandbox ".env"
$VenvDir = Join-Path $Sandbox ".venv"

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataDir "library") | Out-Null

if (!(Test-Path $EnvFile)) {
    if (Test-Path ".env") {
        Copy-Item ".env" $EnvFile
    } else {
        @"
# Sandbox configuration. Fill this through /setup or edit directly.
MODEL_PROVIDER=anthropic
SL_BRIDGE_HOST=127.0.0.1
SL_BRIDGE_PORT=$Port
"@ | Set-Content -Encoding UTF8 $EnvFile
    }
}

if (!(Get-ChildItem -Path (Join-Path $DataDir "library") -Filter "*.md" -ErrorAction SilentlyContinue)) {
    if (Test-Path "data\library") {
        Copy-Item "data\library\*.md" (Join-Path $DataDir "library") -ErrorAction SilentlyContinue
    }
}

if (!(Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
    py -3 -m venv $VenvDir
}

& (Join-Path $VenvDir "Scripts\python.exe") -m pip install -r requirements.txt

$env:TRIXXIE_DATA_DIR = $DataDir
$env:TRIXXIE_ENV_FILE = $EnvFile
$env:MEMORY_DIR = Join-Path $DataDir "memory"
$env:NOTES_DIR = Join-Path $DataDir "notes"
$env:LIBRARY_DIR = Join-Path $DataDir "library"
$env:SL_BRIDGE_HOST = "127.0.0.1"
$env:SL_BRIDGE_PORT = "$Port"

if ($Command -eq "check") {
    & (Join-Path $VenvDir "Scripts\python.exe") check_install.py
    exit $LASTEXITCODE
}

Write-Host "Sandbox data: $DataDir"
Write-Host "Sandbox env:  $EnvFile"
Write-Host "Starting at http://127.0.0.1:$Port/command"
& (Join-Path $VenvDir "Scripts\python.exe") main.py
