param([string]$ModelDir = "models/laya-aml", [int]$Port = 8000)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) { throw "Run scripts/setup.ps1 first." }
if (-not (Test-Path -LiteralPath "dist\index.html")) { throw "Run scripts/setup.ps1 to build the frontend." }
if ($ModelDir) {
    $env:AML_MODEL_DIR = (Resolve-Path -LiteralPath $ModelDir).Path
} else {
    Remove-Item Env:AML_MODEL_DIR -ErrorAction SilentlyContinue
}
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:USE_TF = "0"
Write-Host "TRACE is running at http://127.0.0.1:$Port. Press Ctrl+C to stop."
& .\.venv\Scripts\python.exe -m uvicorn aml.api:app --host 127.0.0.1 --port $Port
