#!/bin/bash
set -e

# Quick setup script for Ubuntu Cloud
# Installs dependencies and runs deploy.sh

echo "🔧 TaskFlow Quick Deploy Setup for Ubuntu"
echo "=========================================="

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo "⚠️  This script needs sudo to install packages."
    echo "Please run with sudo or enter sudo password when prompted."
fi

# 1. Install GitHub CLI
echo "📦 Installing GitHub CLI..."
if ! command -v gh &> /dev/null; then
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
    sudo apt update
    sudo apt install -y gh
    echo "✅ GitHub CLI installed"
else
    echo "✅ GitHub CLI already installed"
fi

# 2. Install Node.js
echo "📦 Installing Node.js..."
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
    echo "✅ Node.js installed"
else
    echo "✅ Node.js already installed"
fi

# 3. Install Railway CLI
echo "📦 Installing Railway CLI..."
if ! command -v railway &> /dev/null; then
    sudo npm install -g @railway/cli
    echo "✅ Railway CLI installed"
else
    echo "✅ Railway CLI already installed"
fi

# 4. Check PATH for npm global bin
NPM_GLOBAL_BIN=$(npm bin -g)
if [[ ":$PATH:" != *":$NPM_GLOBAL_BIN:"* ]]; then
    echo "⚠️  npm global bin not in PATH. Add to ~/.bashrc:"
    echo "export PATH=\"\$PATH:$NPM_GLOBAL_BIN\""
    export PATH="$PATH:$NPM_GLOBAL_BIN"
fi

# 5. Run deploy.sh
echo ""
echo "🔄 Ready to deploy!"
echo "Next steps:"
echo "1. Authenticate GitHub: gh auth login"
echo "2. Authenticate Railway: railway login"
echo "3. Run: ./deploy.sh"
echo ""
echo "Or run them now automatically? (y/N)"
read -r -p "" response
if [[ "$response" =~ ^[Yy]$ ]]; then
    echo "🔐 Please authenticate in the browser prompts that appear..."
    echo ""
    echo "--- GitHub Auth ---"
    gh auth login || true
    echo ""
    echo "--- Railway Auth ---"
    railway login || true
    echo ""
    echo "🚀 Starting deployment..."
    ./deploy.sh
else
    echo "Okay! Run these commands manually when ready:"
    echo "  gh auth login"
    echo "  railway login"
    echo "  ./deploy.sh"
fi