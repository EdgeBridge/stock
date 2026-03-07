#!/bin/bash
# Create us_stock_trading database in coin's PostgreSQL container.
# Run once before first deployment.

set -e

CONTAINER=$(docker ps --filter "ancestor=postgres:16-alpine" --format '{{.Names}}' | head -1)

if [ -z "$CONTAINER" ]; then
    echo "Error: PostgreSQL container not found. Start coin first:"
    echo "  cd ~/coin && docker compose up -d postgres"
    exit 1
fi

echo "Creating us_stock_trading database in container: $CONTAINER"

docker exec "$CONTAINER" psql -U coin -d postgres -c \
    "CREATE USER usstock WITH PASSWORD 'usstock';" 2>/dev/null || echo "User usstock already exists"

docker exec "$CONTAINER" psql -U coin -d postgres -c \
    "CREATE DATABASE us_stock_trading OWNER usstock;" 2>/dev/null || echo "Database us_stock_trading already exists"

docker exec "$CONTAINER" psql -U coin -d postgres -c \
    "GRANT ALL PRIVILEGES ON DATABASE us_stock_trading TO usstock;"

echo "Done. Database us_stock_trading is ready."
