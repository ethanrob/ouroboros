#!/bin/bash
# Quick start script for API Proxy MVP

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Ouroboros API Proxy MVP ===${NC}"
echo ""

# Check environment
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "❌ Error: OPENROUTER_API_KEY not set"
    echo "Set it with: export OPENROUTER_API_KEY='your_key_here'"
    exit 1
fi

echo -e "${GREEN}✅ OPENROUTER_API_KEY found${NC}"
echo ""

# Install dependencies
echo -e "${BLUE}Installing dependencies...${NC}"
pip install -q -r requirements.txt
echo -e "${GREEN}✅ Dependencies installed${NC}"
echo ""

# Start server
echo -e "${BLUE}Starting API server...${NC}"
echo "📍 Local: http://localhost:8000"
echo "📖 Docs: http://localhost:8000/docs"
echo "🛑 Press Ctrl+C to stop"
echo ""

python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
