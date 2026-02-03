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

# Initialize database tables (SQLAlchemy creates them if they don't exist)
echo "Initializing database..."
python -c "from app.database import init_db; init_db()"
echo "Database initialized!"

echo "Starting uvicorn server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 7878 --proxy-headers
