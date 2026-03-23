#!/bin/bash
set -e

echo "⏳ Waiting for PostgreSQL to be ready..."
# Wait for database to accept connections
MAX_RETRIES=30
RETRY_INTERVAL=2
DB_HOST="postgres"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="taskflow"
DB_USER="postgres"
DB_PASSWORD="${POSTGRES_PASSWORD}"

# Test connection using pg_isready or nc
for i in $(seq 1 $MAX_RETRIES); do
    if command -v pg_isready &> /dev/null; then
        if pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" &> /dev/null; then
            echo "✅ PostgreSQL is ready!"
            break
        fi
    else
        # Fallback: try TCP connection
        if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
            echo "✅ PostgreSQL port is open!"
            break
        fi
    fi
    echo "⏳ Waiting for PostgreSQL... (attempt $i/$MAX_RETRIES)"
    sleep $RETRY_INTERVAL
done

if [ $i -eq $MAX_RETRIES ]; then
    echo "❌ PostgreSQL did not become ready in time"
    exit 1
fi

echo "🔧 Running database migrations..."
# Set DATABASE_URL for alembic if not already
export DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
alembic upgrade head || echo "⚠️  Migration failed, maybe tables already exist"

echo "🚀 Starting TaskFlow API on port $PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"