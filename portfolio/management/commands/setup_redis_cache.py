import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.cache import cache
from portfolio.services import StockDataService
from portfolio.models import Stock
import redis

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Setup Redis cache for stock data and test the connection'

    def handle(self, *args, **options):
        self.stdout.write("Starting Redis cache setup...")
        
        # Test Redis connection
        try:
            self.stdout.write("Testing Redis connection...")
            cache.set('test_key', 'test_value', 10)
            test_result = cache.get('test_key')
            
            if test_result == 'test_value':
                self.stdout.write(self.style.SUCCESS("✅ Redis connection successful!"))
            else:
                self.stdout.write(self.style.ERROR(f"❌ Redis test failed. Expected 'test_value', got '{test_result}'"))
                return
        except redis.exceptions.ConnectionError as e:
            self.stdout.write(self.style.ERROR(f"❌ Redis connection error: {str(e)}"))
            self.stdout.write(self.style.WARNING("Make sure Redis is running and accessible."))
            self.stdout.write(self.style.WARNING(f"Current Redis settings:"))
            self.stdout.write(f"  HOST: {settings.REDIS_HOST}")
            self.stdout.write(f"  PORT: {settings.REDIS_PORT}")
            self.stdout.write(f"  DB: {settings.REDIS_DB}")
            self.stdout.write(f"  SSL: {settings.REDIS_SSL}")
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Unknown error: {str(e)}"))
            return
        
        # Initialize stock data in cache
        self.stdout.write("Initializing stock data in cache...")
        stock_service = StockDataService()
        
        # Get all unique symbols from the database
        symbols = list(Stock.objects.values_list('symbol', flat=True))
        
        if not symbols:
            self.stdout.write(self.style.WARNING("No stock symbols found in the database."))
            return
        
        self.stdout.write(f"Found {len(symbols)} stock symbols in the database.")
        self.stdout.write("Caching stock data (this may take a while due to API rate limits)...")
        
        success_count = 0
        error_count = 0
        
        # Cache data for each stock
        for i, symbol in enumerate(symbols, 1):
            try:
                self.stdout.write(f"[{i}/{len(symbols)}] Caching data for {symbol}...")
                stock_data = stock_service.refresh_stock_data(symbol)
                if stock_data:
                    success_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✅ {symbol}: {stock_data.get('company_name', 'Unknown')} - ${stock_data.get('current_price', 0.0)}"))
                else:
                    error_count += 1
                    self.stdout.write(self.style.ERROR(f"  ❌ {symbol}: Failed to cache data"))
            except Exception as e:
                error_count += 1
                self.stdout.write(self.style.ERROR(f"  ❌ {symbol}: Error - {str(e)}"))
        
        # Summary
        self.stdout.write("\nCache initialization complete!")
        self.stdout.write(self.style.SUCCESS(f"✅ Successfully cached data for {success_count} stocks"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"❌ Failed to cache data for {error_count} stocks"))
        
        # Display cache stats if available
        try:
            cache_stats = cache.client._client.info()
            self.stdout.write("\nRedis Cache Statistics:")
            self.stdout.write(f"  Used Memory: {cache_stats.get('used_memory_human', 'Unknown')}")
            self.stdout.write(f"  Number of Keys: {cache_stats.get('db' + settings.REDIS_DB, {}).get('keys', 'Unknown')}")
            self.stdout.write(f"  Connected Clients: {cache_stats.get('connected_clients', 'Unknown')}")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Unable to retrieve cache statistics: {str(e)}"))
        
        self.stdout.write(self.style.SUCCESS("\nRedis cache setup completed!")) 