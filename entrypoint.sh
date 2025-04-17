#!/bin/bash
set -e

echo "Collecting static files..."
python manage.py collectstatic --noinput

# For Cloud SQL in production, we don't need the wait loop
# as the connection happens through Unix socket
DB_HOST="${DB_HOST:-db}"

if [ "$ENVIRONMENT" = "production" ]; then
  echo "Running in production mode with Cloud SQL"
  # Print environment variables for debugging (without showing password)
  echo "DB_HOST: $DB_HOST"
  echo "DB_NAME: $DB_NAME"
  echo "DB_USER: $DB_USER"
else
  # Wait for PostgreSQL in non-production environments
  echo "Waiting for PostgreSQL at $DB_HOST:5432..."
  while ! nc -z $DB_HOST 5432; do
    sleep 1
  done
  echo "PostgreSQL is up - continuing..."
fi

# Run database migrations
echo "python manage.py Before Running Make Migrations"
python manage.py makemigrations

echo "python manage.py Before Running migrate"
python manage.py migrate

echo "python manage.py migrate - Complete..."

# Create superuser if not exists
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ]; then
    python manage.py shell -c "
from django.contrib.auth import get_user_model;
User = get_user_model();
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser(
        username='$DJANGO_SUPERUSER_USERNAME',
        email='$DJANGO_SUPERUSER_EMAIL',
        password='$DJANGO_SUPERUSER_PASSWORD'
    );
    print('Superuser created successfully');
else:
    print('Superuser already exists');
"
fi

# Start the Gunicorn server with PORT env variable for Cloud Run
PORT="${PORT:-8080}"
echo "Starting Gunicorn on port $PORT"
exec gunicorn samaanai.wsgi:application --bind 0.0.0.0:$PORT