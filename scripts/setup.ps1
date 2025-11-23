# AION-AINSTEIN Setup Script for Windows
# Run this in PowerShell from the project root directory

$ErrorActionPreference = "Stop"

Write-Host "===================================" -ForegroundColor Cyan
Write-Host "AION-AINSTEIN Setup (Windows)" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""

# Check for Docker
function Test-Docker {
    Write-Host "Checking requirements..." -ForegroundColor Yellow

    try {
        $null = docker --version
        Write-Host "  Docker: OK" -ForegroundColor Green
    }
    catch {
        Write-Host "  Docker: NOT FOUND" -ForegroundColor Red
        Write-Host "  Please install Docker Desktop for Windows" -ForegroundColor Red
        exit 1
    }

    try {
        $null = docker compose version
        Write-Host "  Docker Compose: OK" -ForegroundColor Green
    }
    catch {
        Write-Host "  Docker Compose: NOT FOUND" -ForegroundColor Red
        exit 1
    }

    try {
        $null = python --version
        Write-Host "  Python: OK" -ForegroundColor Green
    }
    catch {
        Write-Host "  Python: NOT FOUND" -ForegroundColor Red
        Write-Host "  Please install Python 3.10+" -ForegroundColor Red
        exit 1
    }

    Write-Host ""
}

# Start Docker services
function Start-Services {
    Write-Host "Starting Weaviate..." -ForegroundColor Yellow
    docker compose up -d

    Write-Host "Waiting for Weaviate to be ready..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5

    # Wait for Weaviate
    $maxRetries = 30
    $retryCount = 0
    do {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8080/v1/.well-known/ready" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-Host "  Weaviate: Ready" -ForegroundColor Green
                break
            }
        }
        catch {
            $retryCount++
            Write-Host "  Waiting for Weaviate... ($retryCount/$maxRetries)" -ForegroundColor Gray
            Start-Sleep -Seconds 2
        }
    } while ($retryCount -lt $maxRetries)

    if ($retryCount -ge $maxRetries) {
        Write-Host "  Weaviate: TIMEOUT" -ForegroundColor Red
        exit 1
    }

    Write-Host ""
}

# Setup Python environment
function Initialize-PythonEnv {
    Write-Host "Setting up Python environment..." -ForegroundColor Yellow

    # Create venv if it doesn't exist
    if (-not (Test-Path ".venv")) {
        python -m venv .venv
    }

    # Activate venv
    & .\.venv\Scripts\Activate.ps1

    # Upgrade pip
    python -m pip install --upgrade pip

    # Install package
    pip install -e .

    Write-Host "  Python environment: Ready" -ForegroundColor Green
    Write-Host ""
}

# Create .env file
function Initialize-EnvFile {
    if (-not (Test-Path ".env")) {
        Write-Host "Creating .env file from template..." -ForegroundColor Yellow
        Copy-Item .env.example .env
        Write-Host "  .env file: Created" -ForegroundColor Green
        Write-Host ""
        Write-Host "  IMPORTANT: Edit .env and add your OpenAI API key!" -ForegroundColor Yellow
        Write-Host "  notepad .env" -ForegroundColor Gray
        Write-Host ""
    }
    else {
        Write-Host "  .env file: Already exists (skipping)" -ForegroundColor Gray
    }
    Write-Host ""
}

# Check for OpenAI API key
function Test-OpenAIKey {
    if (Test-Path ".env") {
        $envContent = Get-Content ".env" -Raw
        if ($envContent -match "OPENAI_API_KEY=your-openai-api-key-here" -or $envContent -match "OPENAI_API_KEY=$") {
            Write-Host "WARNING: OpenAI API key not configured!" -ForegroundColor Yellow
            Write-Host "Please edit .env and add your OpenAI API key before running 'aion init'" -ForegroundColor Yellow
            Write-Host ""
            return $false
        }
    }
    return $true
}

# Initialize data
function Initialize-Data {
    Write-Host "Initializing data..." -ForegroundColor Yellow
    & .\.venv\Scripts\Activate.ps1
    aion init
    Write-Host ""
}

# Main
function Main {
    Test-Docker
    Start-Services
    Initialize-PythonEnv
    Initialize-EnvFile

    $hasKey = Test-OpenAIKey

    if ($hasKey) {
        Initialize-Data
    }

    Write-Host "===================================" -ForegroundColor Cyan
    Write-Host "Setup Complete!" -ForegroundColor Green
    Write-Host "===================================" -ForegroundColor Cyan
    Write-Host ""

    if (-not $hasKey) {
        Write-Host "Next steps:" -ForegroundColor White
        Write-Host ""
        Write-Host "  1. Add your OpenAI API key to .env:" -ForegroundColor White
        Write-Host "     notepad .env" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  2. Activate the virtual environment:" -ForegroundColor White
        Write-Host "     .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  3. Initialize the data:" -ForegroundColor White
        Write-Host "     aion init" -ForegroundColor Yellow
        Write-Host ""
    }
    else {
        Write-Host "To start using AION-AINSTEIN:" -ForegroundColor White
        Write-Host ""
        Write-Host "  1. Activate the virtual environment:" -ForegroundColor White
        Write-Host "     .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
        Write-Host ""
    }

    Write-Host "  Start interactive mode:" -ForegroundColor White
    Write-Host "     aion interactive" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Or run a query:" -ForegroundColor White
    Write-Host '     aion query "What is IEC 61970?"' -ForegroundColor Yellow
    Write-Host ""
}

Main
