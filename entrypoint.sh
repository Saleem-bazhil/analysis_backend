#!/bin/sh

echo "Running migrations..."
python manage.py migrate --noinput

echo "Seeding users..."
python manage.py seed_users

echo "Starting server..."

exec "$@"
