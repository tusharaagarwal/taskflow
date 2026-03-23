#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "🔍 Verifying secrets configuration..."

# Check if secrets DB exists
if [ ! -f "secrets.db" ]; then
    echo "❌ secrets.db not found. Run: python scripts/secrets_manager.py init"
    exit 1
fi

# Check if key file exists
if [ ! -f ".secrets_key" ]; then
    echo "❌ .secrets_key not found. Run: python scripts/secrets_manager.py init"
    exit 1
fi

# Test retrieval
echo "🧪 Testing secret retrieval..."
if python scripts/secrets_manager.py get SECRET_KEY >/dev/null 2>&1; then
    echo "✅ SECRET_KEY accessible"
else
    echo "⚠️  SECRET_KEY not set. Set it with:"
    echo "   python scripts/secrets_manager.py set SECRET_KEY \"<your-secret>\""
fi

if python scripts/secrets_manager.py get DATABASE_URL >/dev/null 2>&1; then
    echo "✅ DATABASE_URL accessible"
else
    echo "💡 DATABASE_URL not set (optional for local)"
fi

echo "🎉 Secrets verification complete!"