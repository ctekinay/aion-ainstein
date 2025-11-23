#!/bin/bash
# AION-AINSTEIN Setup Script

set -e

echo "==================================="
echo "AION-AINSTEIN Setup"
echo "==================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check for required tools
check_requirements() {
    echo "Checking requirements..."

    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed${NC}"
        exit 1
    fi

    if ! command -v docker compose &> /dev/null; then
        echo -e "${RED}Error: Docker Compose is not installed${NC}"
        exit 1
    fi

    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Error: Python 3 is not installed${NC}"
        exit 1
    fi

    echo -e "${GREEN}All requirements satisfied${NC}"
    echo ""
}

# Start Docker services
start_services() {
    echo "Starting Weaviate and Ollama..."
    docker compose up -d

    echo "Waiting for services to be ready..."
    sleep 10

    # Check if Weaviate is ready
    until curl -s http://localhost:8080/v1/.well-known/ready > /dev/null 2>&1; do
        echo "Waiting for Weaviate..."
        sleep 2
    done

    echo -e "${GREEN}Weaviate is ready${NC}"

    # Check if Ollama is ready
    until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
        echo "Waiting for Ollama..."
        sleep 2
    done

    echo -e "${GREEN}Ollama is ready${NC}"
    echo ""
}

# Pull Ollama models
pull_models() {
    echo "Pulling Ollama models (this may take a while)..."

    echo "Pulling nomic-embed-text..."
    docker compose exec -T ollama ollama pull nomic-embed-text

    echo "Pulling llama3.2..."
    docker compose exec -T ollama ollama pull llama3.2

    echo -e "${GREEN}Models pulled successfully${NC}"
    echo ""
}

# Setup Python environment
setup_python() {
    echo "Setting up Python environment..."

    # Create venv if it doesn't exist
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi

    # Activate venv
    source .venv/bin/activate

    # Install package
    pip install -e .

    echo -e "${GREEN}Python environment ready${NC}"
    echo ""
}

# Create .env file
setup_env() {
    if [ ! -f ".env" ]; then
        echo "Creating .env file from template..."
        cp .env.example .env
        echo -e "${GREEN}.env file created${NC}"
    else
        echo -e "${YELLOW}.env file already exists, skipping${NC}"
    fi
    echo ""
}

# Initialize data
init_data() {
    echo "Initializing data..."
    source .venv/bin/activate
    aion init
    echo ""
}

# Main
main() {
    check_requirements
    start_services
    pull_models
    setup_python
    setup_env
    init_data

    echo "==================================="
    echo -e "${GREEN}Setup Complete!${NC}"
    echo "==================================="
    echo ""
    echo "To start using AION-AINSTEIN:"
    echo ""
    echo "  1. Activate the virtual environment:"
    echo "     source .venv/bin/activate"
    echo ""
    echo "  2. Start interactive mode:"
    echo "     aion interactive"
    echo ""
    echo "  3. Or run a query:"
    echo "     aion query \"What is IEC 61970?\""
    echo ""
}

main "$@"
