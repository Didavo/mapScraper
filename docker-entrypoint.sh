#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
while ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -q; do
    sleep 1
done
echo "PostgreSQL is ready!"

# Initialize database schema if needed
if [ "$INIT_DB" = "true" ]; then
    echo "Initializing database schema..."
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f /app/database/schema.sql 2>/dev/null || echo "Schema already exists or error occurred"
fi

exec "$@"
