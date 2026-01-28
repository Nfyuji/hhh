Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "== Facebook Video Bot: Setup + Run ==" -ForegroundColor Cyan

# Ensure we are in the project directory (this script's folder)
Set-Location -Path $PSScriptRoot

# 1) Create venv if missing
if (!(Test-Path ".\.venv")) {
  Write-Host "Creating virtual environment: .venv" -ForegroundColor Yellow
  python -m venv .venv
}

# 2) Activate venv
Write-Host "Activating virtual environment" -ForegroundColor Yellow
. .\.venv\Scripts\Activate.ps1

# 3) Upgrade pip + install requirements
Write-Host "Upgrading pip" -ForegroundColor Yellow
python -m pip install --upgrade pip

Write-Host "Installing requirements" -ForegroundColor Yellow
pip install -r requirements.txt

# 4) Run app with HTTPS
Write-Host "Starting server with HTTPS: https://127.0.0.1:5000" -ForegroundColor Green
python app.py

