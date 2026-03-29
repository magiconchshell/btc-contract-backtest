#!/bin/bash

# BTC Contract Backtest System - GitHub Setup Script
# This script prepares the project for GitHub upload

echo "🚀 Preparing BTC Contract Backtest System for GitHub..."
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo -e "${RED}❌ Git is not installed. Please install git first.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Git detected${NC}"

# Initialize git repository (if not already)
if [ ! -d ".git" ]; then
    echo "Initializing git repository..."
    git init
    echo -e "${GREEN}✅ Git repository initialized${NC}"
else
    echo -e "${YELLOW}⚠️  Git repository already exists${NC}"
fi

# Add remote origin (you'll need to replace with your actual repo URL)
echo ""
echo "📝 To add remote, run:"
echo "   git remote add origin https://github.com/YOUR_USERNAME/btc-contract-backtest.git"
echo ""

# Create initial commit structure
echo "Creating file structure..."

# Copy files from btc-contract-backtest to github-btc-backtest
cp -r /Users/magiconch/.openclaw/workspace/skills/public/btc-contract-backtest/scripts ./scripts/
cp /Users/magiconch/.openclaw/workspace/skills/public/btc-contract-backtest/SKILL.md .
cp /Users/magiconch/.openclaw/workspace/skills/public/btc-contract-backtest/README.md README_PROJECT.md
cp /Users/magiconch/.openclaw/workspace/skills/public/btc-contract-backtest/PHASES_COMPLETED.md .

echo ""
echo "🎯 Next Steps:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Register a GitHub account at https://github.com/signup"
echo ""
echo "2. Recommended username (in order):"
echo "   - magiconch"
echo "   - magiconchshell"
echo "   - magiconch0328"
echo ""
echo "3. After registration:"
echo "   a) Create new repository: btc-contract-backtest"
echo "   b) Run: git remote add origin https://github.com/YOUR_USERNAME/btc-contract-backtest.git"
echo "   c) Run: git add ."
echo "   d) Run: git commit -m 'Initial commit: BTC Contract Backtest System v4.0'"
echo "   e) Run: git push -u origin main"
echo ""
echo "4. Optional - Customize README.md:"
echo "   - Update YOUR_USERNAME placeholder"
echo "   - Add your email and contact info"
echo "   - Add screenshots or demo videos"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Show file structure
echo "Current file structure:"
ls -la | grep -v "^d" | awk '{print "  " $NF}' | head -20
echo ""

echo -e "${GREEN}✨ Project ready for GitHub upload!${NC}"
echo ""
