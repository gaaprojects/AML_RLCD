param([switch]$WithModel, [string]$Python = "python")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ is required. Pass -Python with the executable path." }
}
$extras = if ($WithModel) { ".[test,ml,data]" } else { ".[test]" }
& .\.venv\Scripts\python.exe -m pip install -e $extras
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed" }
$nodeExecutable = (Get-Command node -ErrorAction Stop).Source
$npmCli = Join-Path (Split-Path $nodeExecutable) "node_modules\npm\bin\npm-cli.js"
if (Test-Path -LiteralPath $npmCli) {
    & $nodeExecutable $npmCli ci
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed" }
    & $nodeExecutable $npmCli run build
} else {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed" }
    & npm.cmd run build
}
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
Write-Host "Ready. Run .\scripts\start.ps1, then open http://127.0.0.1:8000"
