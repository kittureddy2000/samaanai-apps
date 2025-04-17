#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Function to wait for the database to be ready
wait_for_db() {
    echo "Waiting for database..."
    
    # Check if we're connecting to a Cloud SQL instance via Unix socket
    if [[ "$DB_HOST" == /cloudsql/* ]]; then
        echo "Detected Cloud SQL socket connection at $DB_HOST"
        
        # For Cloud SQL, print environment variables for debugging (except password)
        echo "DB_NAME: $DB_NAME"
        echo "DB_USER: $DB_USER"
        echo "DB_HOST: $DB_HOST"
        echo "Password length: ${#DB_PASSWORD}"
        
        # Install pg8000 explicitly if needed
        pip install pg8000==1.30.3 --upgrade
        
        # Try to connect using Python with pg8000 driver for Cloud SQL
        until python -c "
import sys
import os
import pg8000

try:
    print('Connecting to PostgreSQL via pg8000 with Unix socket')
    
    # For Cloud SQL with Unix socket, extract the instance connection name from DB_HOST
    socket_dir = '$DB_HOST'
    print(f'Socket directory: {socket_dir}')
    
    # Use pg8000 to connect, which handles Unix sockets better
    conn = pg8000.connect(
        database='$DB_NAME',
        user='$DB_USER',
        password='$DB_PASSWORD',
        unix_sock=socket_dir + '/.s.PGSQL.5432'
    )
    
    cursor = conn.cursor()
    cursor.execute('SELECT 1')
    result = cursor.fetchone()
    print(f'Database connection successful, test query result: {result}')
    cursor.close()
    conn.close()
except Exception as e:
    print(f'Database connection error: {e}')
    sys.exit(1)
sys.exit(0)
        "; do
            echo "Database is unavailable - sleeping"
            sleep 1
        done
    else
        # Regular TCP connection for non-Cloud SQL or local development
        echo "Using TCP connection to database at $DB_HOST"
        
        # Try to connect using Python with TCP connection
        until python -c "
import sys
import os
import psycopg2
try:
    print(f'Connecting to {os.environ.get(\"DB_NAME\", \"$DB_NAME\")} as {os.environ.get(\"DB_USER\", \"$DB_USER\")} to host {os.environ.get(\"DB_HOST\", \"$DB_HOST\")}')
    
    conn = psycopg2.connect(
        dbname='$DB_NAME',
        user='$DB_USER',
        password='$DB_PASSWORD',
        host='$DB_HOST',
        port='$DB_PORT'
    )
    conn.close()
    print('Database connection successful')
except psycopg2.OperationalError as e:
    print(f'Database connection error: {e}')
    sys.exit(1)
sys.exit(0)
        "; do
            echo "Database is unavailable - sleeping"
            sleep 1
        done
    fi
    
    echo "Database is up - continuing..."
}

# Wait for DB if needed
wait_for_db

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "python manage.py Before Running Make Migrations"
python manage.py makemigrations

echo "python manage.py Before Running migrate"
python manage.py migrate

echo "python manage.py migrate - Complete..."

# Start Gunicorn server
# Use PORT environment variable provided by Cloud Run
# Use environment variables for Gunicorn configuration where possible
WORKERS=${GUNICORN_WORKERS:-1} # Default to 1 worker if not set
THREADS=${GUNICORN_THREADS:-8} # Default to 8 threads if not set
TIMEOUT=${GUNICORN_TIMEOUT:-0} # Default to 0 (infinite) if not set
PORT=${PORT:-8080} # Default to 8080 if not set

echo "Starting Gunicorn server on port $PORT with $WORKERS workers and $THREADS threads..."
exec gunicorn samaanai.wsgi:application \
    --bind 0.0.0.0:$PORT \
    --workers $WORKERS \
    --threads $THREADS \
    --timeout $TIMEOUT