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

# Special handling for migrations in case tables are missing
echo "Checking database tables"

# First, try to fake-initial migrations to handle missing tables
echo "Attempting to fake initial migrations (in case tables were manually deleted)..."
python manage.py migrate --fake-initial || echo "Fake initial migration failed, continuing with regular migration"

# Run database migrations with better error handling
echo "Running makemigrations..."
python manage.py makemigrations || { echo "makemigrations failed but continuing"; }

echo "Running migrate..."
# Try migrating with a fake-initial first if there are issues
python manage.py migrate || {
  echo "Migration failed. Attempting recovery..."
  
  # Try creating the tables that might be missing (may fail for some tables)
  echo "Trying to create missing tables..."
  for app in task_management portfolio core spreturn; do
    echo "Trying to recreate tables for $app"
    # Try zeroed migrations first
    python manage.py migrate $app zero --fake || echo "Failed to zero migrations for $app, continuing"
    # Then try migrating
    python manage.py migrate $app --fake-initial || echo "Failed to migrate $app with fake-initial, continuing"
  done
  
  # Try a regular migrate again
  echo "Retrying regular migrate after recovery attempt..."
  python manage.py migrate || echo "Migration still failed, but continuing to start the server anyway"
}

echo "Migration process complete (with or without errors)"

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