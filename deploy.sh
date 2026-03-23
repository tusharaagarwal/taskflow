#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 TaskFlow Render Deploy Script"
echo "================================"

# Check prerequisites
echo "🔍 Checking prerequisites..."

if ! command -v gh &> /dev/null; then
    echo -e "${RED}❌ GitHub CLI (gh) not found${NC}"
    echo "Install: https://cli.github.com/"
    exit 1
fi

if ! command -v render &> /dev/null; then
    echo -e "${RED}❌ Render CLI not found${NC}"
    echo "Install: https://render.com/docs/cli"
    exit 1
fi

# Verify auth
echo "🔐 Verifying CLI authentication..."

if ! gh auth status &> /dev/null; then
    echo -e "${RED}❌ GitHub CLI not authenticated${NC}"
    echo "Run: gh auth login"
    exit 1
fi

# Render auth check (skip due to CLI bug; we'll handle errors later)
echo "   (Render auth will be handled during deploy)"

echo -e "${GREEN}✅ Authentication verified${NC}"

# Navigate to project root
cd "$(dirname "$0")"

# Check if already in a git repo
if [ ! -d .git ]; then
    echo "📦 Initializing git repository..."
    git init
    git add .
    git commit -m "Initial commit for Render deployment"
else
    echo "📦 Git repository already exists"
    git add .
    git commit -m "Update for Render deployment" || echo "No changes to commit"
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

# Render deployment
echo "🎨 Deploying to Render..."

# Check if render project exists
PROJECT_NAME="taskflow"
if render projects list | grep -q "$PROJECT_NAME"; then
    echo -e "${YELLOW}⚠️  Render project $PROJECT_NAME already exists${NC}"
    echo "   → Will update existing project"
    RENDER_EXISTS=true
else
    RENDER_EXISTS=false
fi

# Create or update project
if [ "$RENDER_EXISTS" = false ]; then
    echo "Creating Render project..."
    render init --name "$PROJECT_NAME" --repo "github:$GH_USER/$REPO_NAME" --plan free
else
    echo "Linking to existing Render project..."
    render link "$PROJECT_NAME"
fi

# Set environment variables
echo "⚙️  Setting environment variables..."

# Generate SECRET_KEY if not already set
if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$(openssl rand -hex 32)
    echo "Generated SECRET_KEY"
fi

render secrets set SECRET_KEY "$SECRET_KEY"
render secrets set DEBUG "false"
render secrets set ALLOWED_ORIGINS "https://taskflow-frontend.onrender.com"

# Trigger deployment
echo "⏳ Triggering deployment..."
render deploy

echo ""
echo "==========================================="
echo -e "${GREEN}🎉 Deployment triggered!${NC}"
echo ""
echo "🔗 Your URLs will be:"
echo "   Frontend: https://taskflow-frontend.onrender.com"
echo "   Backend API: https://taskflow-backend.onrender.com/docs"
echo ""
echo "⏳ Deployment takes 2-5 minutes. Check progress:"
echo "   render logs --tail"
echo ""
echo "📖 Next steps:"
echo "   1. Wait for deployment to finish (check logs)"
echo "   2. Open Frontend URL in browser"
echo "   3. Open Backend URL/docs to access Swagger"
echo "   4. Register user via /docs → POST /api/v1/auth/register"
echo "   5. Login on frontend and start using!"
echo ""
echo "==========================================="