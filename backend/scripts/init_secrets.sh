#!/bin/bash
set -e

echo "🔐 Initializing SQLite Secrets Manager..."

cd "$(dirname "$0")/.."

# Create secrets DB and key if not exist
python scripts/secrets_manager.py init

# Check if SECRET_KEY exists
if ! python scripts/secrets_manager.py get SECRET_KEY >/dev/null 2>&1; then
    echo "⚠️  No SECRET_KEY found. Generating one..."
    SECRET=$(openssl rand -hex 32)
    python scripts/secrets_manager.py set SECRET_KEY "$SECRET"
    echo "✅ SECRET_KEY set"
fi

# Check if DATABASE_URL exists (for local)
if ! python scripts/secrets_manager.py get DATABASE_URL >/dev/null 2>&1; then
    echo "💡 Tip: Set DATABASE_URL for local DB connection:"
    echo "   python scripts/secrets_manager.py set DATABASE_URL \"postgresql://...\""
fi

echo "🎉 Secrets ready! Remember:"
echo "   - secrets.db and .secrets_key are in .gitignore"
echo "   - To list secrets: python scripts/secrets_manager.py list"
echo "   - To get a secret: python scripts/secrets_manager.py get <key>"