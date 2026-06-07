param(
    [Parameter(Mandatory = $true)]
    [string]$Remote,
    [Parameter(Mandatory = $true)]
    [string]$RemotePath,
    [string]$Target = ".sandbox\windows",
    [switch]$IncludeEnv,
    [switch]$IncludeChroma
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$TargetPath = Join-Path $Root $Target
New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null

$excludes = @()
if (!$IncludeChroma) {
    $excludes += "--exclude=data/memory/chroma"
    $excludes += "--exclude=data/.cache"
}
if (!$IncludeEnv) {
    $excludes += "--exclude=.env"
}

$excludeArgs = $excludes -join " "
$remoteCommand = "cd '$RemotePath' && tar $excludeArgs -czf - data"
if ($IncludeEnv) {
    $remoteCommand = "cd '$RemotePath' && tar $excludeArgs -czf - data .env"
}

ssh $Remote $remoteCommand | tar -xzf - -C $TargetPath

if (!$IncludeEnv -and !(Test-Path (Join-Path $TargetPath ".env"))) {
    @"
# Sandbox configuration. Fill this through /setup or copy live env intentionally.
MODEL_PROVIDER=anthropic
SL_BRIDGE_HOST=127.0.0.1
SL_BRIDGE_PORT=18080
"@ | Set-Content -Encoding UTF8 (Join-Path $TargetPath ".env")
}

Write-Host "Pulled live data into $TargetPath"
Write-Host "Chroma/cache copied: $IncludeChroma"
Write-Host ".env copied: $IncludeEnv"
