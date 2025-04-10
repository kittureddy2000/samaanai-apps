#!/bin/sh

# Exit immediately if a command exits with a non-zero status nad 
set -e

echo "Collecting static files..."
python manage.py collectstatic --noinput



DB_HOST="${DB_HOST:-db}"

# Wait for PostgreSQL to be ready
if [ "$ENVIRONMENT" != "production" ]; then

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

# Start the Gunicorn server
gunicorn --bind 0.0.0.0:8080 samaanai.wsgi:application

echo "gunicorn started"