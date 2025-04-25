from django.test.runner import DiscoverRunner
from django.db import connections
from django.core.management import call_command

class ExplicitMigrationTestRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        # Set up databases as normal
        old_config = super().setup_databases(**kwargs)
        
        # Force migrations to run
        call_command('migrate')
        
        return old_config
