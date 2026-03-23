#!/bin/bash
set -e

echo "🔧 Running migrations..."
alembic upgrade head || echo "⚠️  Migration skipped (tables may already exist)"

echo "🚀 Starting server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
