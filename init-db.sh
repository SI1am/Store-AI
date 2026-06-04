#!/bin/bash
set -e

DB_URL=${DATABASE_URL:-"postgresql://user:password@localhost:5432/retail_db"}
echo "Connecting to database at: $DB_URL"

# Wait for DB to be ready
until psql "$DB_URL" -c '\q' 2>/dev/null; do
  echo "Database is unavailable - sleeping"
  sleep 1
done

echo "Database is up - running migrations"

# Run migrations in order
for file in sql/00*.sql; do
  echo "Applying migration: $file"
  psql "$DB_URL" -f "$file"
done

echo "Database migrations successfully applied!"
