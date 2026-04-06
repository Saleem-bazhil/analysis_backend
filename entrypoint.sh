#!/bin/sh

echo "📦 Running migrations..."
python manage.py migrate --noinput

echo "🚀 Starting server..."

exec "$@"