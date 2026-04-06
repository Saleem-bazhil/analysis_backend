#!/bin/sh

echo "⏳ Waiting for PostgreSQL..."

while ! nc -z $DB_HOST 5432; do
  sleep 1
done

echo "✅ PostgreSQL ready"

echo "📦 Running migrations..."
python manage.py migrate --noinput

echo "🚀 Starting server..."

exec "$@"