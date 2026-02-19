#!/bin/bash
# Run backend tests inside the Docker container
# Usage: bash scripts/run-tests.sh [extra pytest args]
# Examples:
#   bash scripts/run-tests.sh
#   bash scripts/run-tests.sh -k test_auth
#   bash scripts/run-tests.sh --tb=long -v

set -e

echo "=== Alejandría Backend Tests ==="
echo ""

# Check if container is running
if ! docker compose ps backend | grep -q "running\|Up"; then
    echo "Starting backend container..."
    docker compose up -d backend
    sleep 3
fi

# Run tests
docker compose exec -T backend python -m pytest tests/ -v --tb=short "$@"
