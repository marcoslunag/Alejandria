#!/bin/bash
set -e

echo "Starting Alejandria Backend..."

# Wait for database to be ready
echo "Waiting for database..."
until pg_isready -h postgres -p 5432 -U ${POSTGRES_USER:-manga}; do
    echo "Database is unavailable - sleeping"
    sleep 2
done
echo "Database is ready!"

# Run database migrations
echo "Running database migrations..."
alembic upgrade head || {
    echo "Migration failed or no migrations needed"
    # If alembic fails, ensure tables exist via SQLAlchemy
    python -c "from app.database import init_db; init_db()"
}

echo "Starting uvicorn server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 7878 --proxy-headers
