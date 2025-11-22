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
    Write-Host "Starting Weaviate and Ollama..." -ForegroundColor Yellow
    docker compose up -d

    Write-Host "Waiting for services to be ready..." -ForegroundColor Yellow
    Start-Sleep -Seconds 10

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

    # Wait for Ollama
    $retryCount = 0
    do {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-Host "  Ollama: Ready" -ForegroundColor Green
                break
            }
        }
        catch {
            $retryCount++
            Write-Host "  Waiting for Ollama... ($retryCount/$maxRetries)" -ForegroundColor Gray
            Start-Sleep -Seconds 2
        }
    } while ($retryCount -lt $maxRetries)

    Write-Host ""
}

# Pull Ollama models
function Get-OllamaModels {
    Write-Host "Pulling Ollama models (this may take a while)..." -ForegroundColor Yellow

    Write-Host "  Pulling nomic-embed-text..." -ForegroundColor Gray
    docker compose exec -T ollama ollama pull nomic-embed-text

    Write-Host "  Pulling llama3.2..." -ForegroundColor Gray
    docker compose exec -T ollama ollama pull llama3.2

    Write-Host "  Models: Ready" -ForegroundColor Green
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
    }
    else {
        Write-Host "  .env file: Already exists (skipping)" -ForegroundColor Gray
    }
    Write-Host ""
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
    Get-OllamaModels
    Initialize-PythonEnv
    Initialize-EnvFile
    Initialize-Data

    Write-Host "===================================" -ForegroundColor Cyan
    Write-Host "Setup Complete!" -ForegroundColor Green
    Write-Host "===================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To start using AION-AINSTEIN:" -ForegroundColor White
    Write-Host ""
    Write-Host "  1. Activate the virtual environment:" -ForegroundColor White
    Write-Host "     .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  2. Start interactive mode:" -ForegroundColor White
    Write-Host "     aion interactive" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  3. Or run a query:" -ForegroundColor White
    Write-Host '     aion query "What is IEC 61970?"' -ForegroundColor Yellow
    Write-Host ""
}

Main
