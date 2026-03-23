#!/bin/bash
set -e

echo "🔧 Running database migrations..."
alembic upgrade head

echo "🚀 Starting TaskFlow API..."
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT