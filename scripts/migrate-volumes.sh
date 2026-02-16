#!/bin/bash
# Migration script: Rename Docker volumes from 'manga' to 'library'
# Run this ONCE before starting the updated docker-compose
#
# Usage: bash scripts/migrate-volumes.sh

set -e

echo "=== Alejandria Volume Migration ==="
echo "Migrating: manga -> library"
echo ""

# Stop services first
echo "Stopping services..."
docker compose down 2>/dev/null || true

# Check if old volume exists
OLD_VOL=$(docker volume ls -q | grep -E "manga$" | head -1)
NEW_VOL="${OLD_VOL/manga/library}"

if [ -z "$OLD_VOL" ]; then
    echo "No 'manga' volume found. Nothing to migrate."
    exit 0
fi

echo "Old volume: $OLD_VOL"
echo "New volume: $NEW_VOL"

# Create new volume
docker volume create "$NEW_VOL" 2>/dev/null || true

# Copy data from old to new using a temp container
echo "Copying data..."
docker run --rm \
    -v "$OLD_VOL":/source:ro \
    -v "$NEW_VOL":/dest \
    alpine sh -c "cp -a /source/. /dest/"

echo "Data copied successfully."
echo ""
echo "Old volume '$OLD_VOL' has been preserved (not deleted)."
echo "After verifying everything works, you can remove it with:"
echo "  docker volume rm $OLD_VOL"
echo ""
echo "=== Migration complete ==="
