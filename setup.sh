#!/usr/bin/env bash
# AInstein Bootstrap Script
# Validates prerequisites, patches .env, starts services, and initializes the database.
# Works on macOS and Linux. Windows users: run via WSL or Git Bash.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }

CHANGES=()

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  AInstein Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Prerequisites ──────────────────────────────────────────────────────────

echo "Checking prerequisites..."

# Python 3.11-3.12
PYTHON_OK=false
for cmd in python3.12 python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        if [[ "$PY_VER" == "3.11" || "$PY_VER" == "3.12" ]]; then
            ok "Python $PY_VER ($cmd)"
            PYTHON_OK=true
            break
        fi
    fi
done
if [ "$PYTHON_OK" = false ]; then
    fail "Python 3.11 or 3.12 required (found: ${PY_VER:-none})"
    exit 1
fi

# Docker or Podman
COMPOSE_CMD=""
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    ok "Docker"
    COMPOSE_CMD="docker compose"
elif command -v podman &>/dev/null; then
    ok "Podman"
    if command -v podman-compose &>/dev/null; then
        COMPOSE_CMD="podman-compose"
    else
        fail "podman-compose not found (install: pip install podman-compose)"
        exit 1
    fi
else
    fail "Docker or Podman required"
    exit 1
fi

# uv
if command -v uv &>/dev/null; then
    ok "uv"
else
    fail "uv not found (install: https://docs.astral.sh/uv/)"
    exit 1
fi

# Ollama
OLLAMA_OK=false
if command -v ollama &>/dev/null; then
    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        ok "Ollama (running)"
        OLLAMA_OK=true
        # Check models
        MODELS=$(curl -s http://localhost:11434/api/tags 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(' '.join(m['name'] for m in data.get('models', [])))
except: pass
" 2>/dev/null || echo "")
        for model in nomic-embed-text-v2-moe gpt-oss:20b; do
            if echo "$MODELS" | grep -q "$model"; then
                ok "Model: $model"
            else
                warn "Model missing: $model — run: ollama pull $model"
            fi
        done
    else
        warn "Ollama installed but not running — run: ollama serve"
    fi
else
    warn "Ollama not found (optional — needed for local LLM mode)"
fi

echo ""

# ── 2. Environment file ──────────────────────────────────────────────────────

echo "Checking .env..."

if [ ! -f .env ]; then
    cp .env.example .env
    ok "Created .env from .env.example"
    CHANGES+=("Created .env from template")
    warn "Add your API keys to .env before running AInstein"
else
    # Back up before patching
    cp .env .env.bak

    patched=0

    # Fix stale Weaviate port (old: 8090, correct: 8080 — default)
    if grep -q 'WEAVIATE_URL=http://localhost:8090' .env 2>/dev/null; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' 's|WEAVIATE_URL=http://localhost:8090|WEAVIATE_URL=http://localhost:8080|' .env
        else
            sed -i 's|WEAVIATE_URL=http://localhost:8090|WEAVIATE_URL=http://localhost:8080|' .env
        fi
        warn "Patched WEAVIATE_URL: 8090 → 8080"
        CHANGES+=("WEAVIATE_URL: 8090 → 8080")
        patched=1
    fi

    # Fix stale gRPC port (old: 50061, correct: 50051 — default)
    if grep -q 'WEAVIATE_GRPC_URL=localhost:50061' .env 2>/dev/null; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' 's|WEAVIATE_GRPC_URL=localhost:50061|WEAVIATE_GRPC_URL=localhost:50051|' .env
        else
            sed -i 's|WEAVIATE_GRPC_URL=localhost:50061|WEAVIATE_GRPC_URL=localhost:50051|' .env
        fi
        warn "Patched WEAVIATE_GRPC_URL: 50061 → 50051"
        CHANGES+=("WEAVIATE_GRPC_URL: 50061 → 50051")
        patched=1
    fi

    # Fix stale SKOSMOS port (old: 8080, correct: 8090)
    if grep -q 'SKOSMOS_URL=http://localhost:8080' .env 2>/dev/null; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' 's|SKOSMOS_URL=http://localhost:8080|SKOSMOS_URL=http://localhost:8090|' .env
        else
            sed -i 's|SKOSMOS_URL=http://localhost:8080|SKOSMOS_URL=http://localhost:8090|' .env
        fi
        warn "Patched SKOSMOS_URL: 8080 → 8090"
        CHANGES+=("SKOSMOS_URL: 8080 → 8090")
        patched=1
    fi

    # Add missing keys from .env.example
    for key in WEAVIATE_URL WEAVIATE_GRPC_URL WEAVIATE_IS_LOCAL SKOSMOS_URL; do
        if ! grep -q "^${key}=" .env 2>/dev/null; then
            value=$(grep "^${key}=" .env.example 2>/dev/null || echo "")
            if [ -n "$value" ]; then
                echo "$value" >> .env
                warn "Added missing: $key"
                CHANGES+=("Added $key")
                patched=1
            fi
        fi
    done

    # Generate Fernet key if still placeholder
    if grep -q "FERNET_KEY='generate-your-own-fernet-key-here'" .env 2>/dev/null; then
        FERNET=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "")
        if [ -n "$FERNET" ]; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|FERNET_KEY='generate-your-own-fernet-key-here'|FERNET_KEY='${FERNET}'|" .env
            else
                sed -i "s|FERNET_KEY='generate-your-own-fernet-key-here'|FERNET_KEY='${FERNET}'|" .env
            fi
            ok "Generated FERNET_KEY"
            CHANGES+=("Generated FERNET_KEY")
            patched=1
        fi
    fi

    if [ $patched -eq 0 ]; then
        ok ".env is up to date"
        rm -f .env.bak
    else
        ok "Backup saved to .env.bak"
    fi
fi

echo ""

# ── 3. Docker containers ─────────────────────────────────────────────────────

echo "Starting services..."

# Stop existing container if running
if docker ps -q -f name=weaviate-ainstein-dev &>/dev/null 2>&1; then
    docker stop weaviate-ainstein-dev &>/dev/null 2>&1 || true
fi

$COMPOSE_CMD up -d
ok "Docker containers started"

# Wait for Weaviate healthcheck
echo "  Waiting for Weaviate..."
WEAVIATE_URL=$(grep '^WEAVIATE_URL=' .env 2>/dev/null | cut -d= -f2 || echo "http://localhost:8080")
for i in $(seq 1 30); do
    if curl -s "${WEAVIATE_URL}/v1/.well-known/ready" &>/dev/null; then
        ok "Weaviate ready"
        break
    fi
    if [ "$i" -eq 30 ]; then
        fail "Weaviate not ready after 30s — check: docker logs weaviate-ainstein-dev"
        exit 1
    fi
    sleep 1
done

echo ""

# ── 4. Python environment ────────────────────────────────────────────────────

echo "Installing Python dependencies..."
uv sync
ok "Dependencies installed"

echo ""

# ── 5. Database initialization ────────────────────────────────────────────────

echo "Initializing database..."
python -m src.aion.cli init --chunked
ok "Database initialized"

echo ""

# ── 6. Summary ────────────────────────────────────────────────────────────────

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Status
WEAVIATE_READY=false
if curl -s "${WEAVIATE_URL}/v1/.well-known/ready" &>/dev/null; then
    ok "Weaviate: running on ${WEAVIATE_URL}"
    WEAVIATE_READY=true
else
    fail "Weaviate: not responding"
fi

if [ "$OLLAMA_OK" = true ]; then
    ok "Ollama: running"
else
    warn "Ollama: not running (needed for local LLM mode)"
fi

if [ ${#CHANGES[@]} -gt 0 ]; then
    echo ""
    echo "  Changes made:"
    for c in "${CHANGES[@]}"; do
        echo "    - $c"
    done
fi

echo ""
echo "  Run:  python -m src.aion.chat_ui --port 8081"
echo "  Open: http://localhost:8081"
echo ""
