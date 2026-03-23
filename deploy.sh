#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 TaskFlow Railway Deploy Script"
echo "================================"

# Check prerequisites
echo "🔍 Checking prerequisites..."

if ! command -v gh &> /dev/null; then
    echo -e "${RED}❌ GitHub CLI (gh) not found${NC}"
    echo "Install: https://cli.github.com/"
    exit 1
fi

if ! command -v railway &> /dev/null; then
    echo -e "${RED}❌ Railway CLI not found${NC}"
    echo "Install: https://docs.railway.app/develop/cli"
    exit 1
fi

# Verify auth
echo "🔐 Verifying CLI authentication..."

if ! gh auth status &> /dev/null; then
    echo -e "${RED}❌ GitHub CLI not authenticated${NC}"
    echo "Run: gh auth login"
    exit 1
fi

if ! railway whoami &> /dev/null; then
    echo -e "${RED}❌ Railway CLI not authenticated${NC}"
    echo "Run: railway login"
    exit 1
fi

echo -e "${GREEN}✅ Authentication verified${NC}"

# Navigate to project root
cd "$(dirname "$0")"

# Check if already in a git repo
if [ ! -d .git ]; then
    echo "📦 Initializing git repository..."
    git init
    git add .
    git commit -m "Initial commit for Railway deployment"
else
    echo "📦 Git repository already exists"
    git add .
    git commit -m "Update for Railway deployment" || echo "No changes to commit"
fi

# GitHub repo setup
echo "🐙 Setting up GitHub repository..."

# Get GitHub username
GH_USER=$(gh api user --jq .login)
REPO_NAME="taskflow"

# Check if repo exists
if gh repo view "$GH_USER/$REPO_NAME" &> /dev/null; then
    echo -e "${YELLOW}⚠️  Repo $REPO_NAME already exists${NC}"
    echo "   → Will push to existing repo (no deletion)"
fi

# Create repo if not exists
if ! gh repo view "$GH_USER/$REPO_NAME" &> /dev/null; then
    echo "Creating GitHub repo: $GH_USER/$REPO_NAME"
    gh repo create "$REPO_NAME" --public --source=. --remote=origin --push
else
    # Set remote if not set
    if ! git remote get-url origin &> /dev/null; then
        git remote add origin "https://github.com/$GH_USER/$REPO_NAME.git"
    fi
    # Push current branch (could be master or main)
    CURRENT_BRANCH=$(git branch --show-current)
    git push -u origin "$CURRENT_BRANCH"
fi

echo -e "${GREEN}✅ GitHub repository ready: https://github.com/$GH_USER/$REPO_NAME${NC}"

# Railway deployment
echo "🚂 Deploying to Railway..."

# Check if railway project exists
PROJECT_NAME="taskflow"
if railway ls | grep -q "$PROJECT_NAME"; then
    echo -e "${YELLOW}⚠️  Railway project $PROJECT_NAME already exists${NC}"
    echo "   → Will link to existing project (no deletion)"
fi

# Create or link project
if ! railway ls | grep -q "$PROJECT_NAME"; then
    echo "Creating Railway project from GitHub repo..."
    railway link --create "$PROJECT_NAME"
else
    railway link "$PROJECT_NAME"
fi

# Set environment variables
echo "⚙️  Setting environment variables..."

# Generate SECRET_KEY if not already set
if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$(openssl rand -hex 32)
    echo "Generated SECRET_KEY"
fi

railway variables set SECRET_KEY "$SECRET_KEY"
railway variables set DEBUG "false"
# Railway auto-sets DATABASE_URL when PostgreSQL plugin added

# Add PostgreSQL plugin
echo "🗄️  Adding PostgreSQL database..."
if ! railway plugins ls | grep -q "postgresql"; then
    railway plugins add postgresql
fi

# Wait for deploy
echo "⏳ Triggering deployment..."
railway up

# Get URLs
echo "🔗 Fetching deployment URLs..."
FRONTEND_URL=$(railway domain --json | jq -r '.[] | select(.name=="frontend") | .url' 2>/dev/null || echo "")
BACKEND_URL=$(railway domain --json | jq -r '.[] | select(.name=="backend") | .url' 2>/dev/null || echo "")

if [ -z "$FRONTEND_URL" ]; then
    # Fallback: try to get from railway domains
    FRONTEND_URL=$(railway domain | grep -E 'https://.*railway.app' | head -1 || echo "")
fi

echo ""
echo "==========================================="
echo -e "${GREEN}🎉 Deployment complete!${NC}"
echo ""
echo "🔗 Your URLs:"
if [ -n "$FRONTEND_URL" ]; then
    echo "   Frontend: $FRONTEND_URL"
else
    echo "   Frontend: (check Railway dashboard → Services → frontend → Domains)"
fi
if [ -n "$BACKEND_URL" ]; then
    echo "   Backend API: $BACKEND_URL/docs"
else
    echo "   Backend API: (check Railway dashboard → Services → backend → Domains)"
fi
echo ""
echo "📖 Next steps:"
echo "   1. Open Frontend URL in browser"
echo "   2. Open Backend URL/docs to access Swagger"
echo "   3. Register user via /docs → POST /api/v1/auth/register"
echo "   4. Login on frontend and start using!"
echo ""
echo "==========================================="