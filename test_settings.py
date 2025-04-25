from samaanai.settings import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': '/app/test_db.sqlite3',
    }
}

# Debug migrations
MIGRATION_MODULES = {}

# Use our custom test runner
TEST_RUNNER = 'task_management.tests.test_runner.ExplicitMigrationTestRunner'