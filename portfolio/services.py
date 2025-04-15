import logging
import json
from decimal import Decimal
from django.core.cache import cache
from django.conf import settings
import redis
import datetime
import time
from functools import lru_cache

from .api import fetch_stock_data, StockAPIError
from .models import Stock

logger = logging.getLogger(__name__)

# In-memory cache when Redis is unavailable
MEMORY_CACHE = {}
MEMORY_CACHE_TIMESTAMPS = {}
MEMORY_CACHE_TIMEOUT = 60 * 15  # 15 minutes

class StockDataService:
    """
    Service to handle stock data retrieval with Redis caching
    This replaces direct database storage with a cache-first approach
    """
    
    def __init__(self):
        self.price_cache_timeout = getattr(settings, 'STOCK_PRICE_CACHE_TIMEOUT', 60 * 15)  # 15 minutes default
        self.details_cache_timeout = getattr(settings, 'STOCK_DETAILS_CACHE_TIMEOUT', 60 * 60 * 24)  # 24 hours default
        self.redis_available = self._check_redis_connection()
        # Track which symbols we're currently fetching to prevent duplicate calls
        self.currently_fetching = set()
    
    def _check_redis_connection(self):
        """Check if Redis is available"""
        try:
            cache.set('redis_test', 'test', 1)
            return cache.get('redis_test') == 'test'
        except (redis.exceptions.ConnectionError, redis.exceptions.RedisError):
            logger.warning("Redis is not available - will use in-memory cache instead")
            return False
    
    def get_cache_key(self, symbol, data_type='full'):
        """Generate a consistent cache key for stock data"""
        return f"stock:{symbol.upper()}:{data_type}"
    
    def _get_from_memory_cache(self, symbol):
        """Get data from memory cache if valid"""
        current_time = time.time()
        timestamp = MEMORY_CACHE_TIMESTAMPS.get(symbol)
        
        if symbol in MEMORY_CACHE and timestamp and (current_time - timestamp) < MEMORY_CACHE_TIMEOUT:
            logger.debug(f"Memory cache hit for {symbol}")
            return MEMORY_CACHE.get(symbol)
        return None
        
    def _set_in_memory_cache(self, symbol, data):
        """Store data in memory cache with timestamp"""
        MEMORY_CACHE[symbol] = data
        MEMORY_CACHE_TIMESTAMPS[symbol] = time.time()
        logger.debug(f"Stored {symbol} in memory cache")
    
    def get_stock_data(self, symbol):
        """
        Get stock data from cache or API
        Returns a dictionary with stock information
        """
        symbol = symbol.upper()
        
        # Check if another thread/request is already fetching this symbol
        if symbol in self.currently_fetching:
            logger.info(f"Already fetching {symbol}, using default data")
            # Return basic data while it's being fetched
            return self._get_default_stock_data(symbol)
        
        # Try to get from Redis cache
        if self.redis_available:
            try:
                cache_key = self.get_cache_key(symbol)
                cached_data = cache.get(cache_key)
                if cached_data:
                    logger.debug(f"Redis cache hit for {symbol}")
                    return json.loads(cached_data)
            except (redis.exceptions.RedisError, json.JSONDecodeError, Exception) as e:
                logger.warning(f"Redis error when getting {symbol}: {str(e)}")
        
        # Try in-memory cache if Redis failed or is unavailable
        memory_cached_data = self._get_from_memory_cache(symbol)
        if memory_cached_data:
            return memory_cached_data
            
        # If we get here, need to fetch from API
        logger.info(f"Getting data for {symbol} directly from API")
        
        # Add to currently fetching set
        self.currently_fetching.add(symbol)
        try:
            return self.refresh_stock_data(symbol)
        finally:
            # Always remove from currently fetching set, even if an error occurred
            self.currently_fetching.discard(symbol)
    
    def _get_default_stock_data(self, symbol):
        """Return default stock data for a symbol"""
        # Try to get stock from database for basic info
        stock = Stock.objects.filter(symbol=symbol).first()
        name = stock.name if stock else symbol
        
        return {
            'symbol': symbol,
            'company_name': name,
            'current_price': 0.0,
            'day_change': 0.0,
            'day_change_percentage': 0.0,
            'last_updated': str(int(datetime.datetime.now().timestamp()))
        }
    
    def refresh_stock_data(self, symbol):
        """
        Fetch fresh stock data from the API and update cache
        Returns the fetched data
        """
        symbol = symbol.upper()
        
        try:
            # Fetch from API
            price, company_name, additional_data = fetch_stock_data(symbol)
            
            # Update or create the basic stock record in database
            stock, created = Stock.objects.get_or_create(symbol=symbol)
            if not stock.name and company_name:
                stock.name = company_name
                stock.save()
            
            # Prepare the full data
            stock_data = {
                'symbol': symbol,
                'company_name': company_name,
                'current_price': float(price),  # Convert Decimal to float for JSON serialization
                'day_change': float(additional_data.get('day_change', 0)),
                'day_change_percentage': float(additional_data.get('day_change_percentage', 0)),
                'fifty_two_week_high': float(additional_data['fifty_two_week_high']) if additional_data.get('fifty_two_week_high') else None,
                'fifty_two_week_low': float(additional_data['fifty_two_week_low']) if additional_data.get('fifty_two_week_low') else None,
                'pe_ratio': float(additional_data['pe_ratio']) if additional_data.get('pe_ratio') else None,
                'dividend_yield': float(additional_data['dividend_yield']) if additional_data.get('dividend_yield') else None,
                'last_updated': str(int(datetime.datetime.now().timestamp()))
            }
            
            # Store in memory cache
            self._set_in_memory_cache(symbol, stock_data)
            
            # Cache the data if Redis is available
            if self.redis_available:
                try:
                    cache_key = self.get_cache_key(symbol)
                    price_key = self.get_cache_key(symbol, 'price')
                    
                    # Extract just the price for shorter cache time
                    price_data = {
                        'current_price': float(price),
                        'day_change': float(additional_data.get('day_change', 0)),
                        'day_change_percentage': float(additional_data.get('day_change_percentage', 0)),
                    }
                    
                    # Cache the data
                    cache.set(cache_key, json.dumps(stock_data), self.details_cache_timeout)
                    cache.set(price_key, json.dumps(price_data), self.price_cache_timeout)
                    logger.info(f"Updated Redis cache for {symbol}")
                except (redis.exceptions.RedisError, Exception) as e:
                    logger.warning(f"Failed to cache data in Redis for {symbol}: {str(e)}")
            
            return stock_data
            
        except StockAPIError as e:
            logger.error(f"API error for {symbol}: {str(e)}")
            
            # Check if this is a rate limit error
            if "rate limit" in str(e).lower():
                logger.warning(f"Rate limit hit for {symbol}, using cached or default data")
                
                # Try Redis cache first (even if expired)
                if self.redis_available:
                    try:
                        cache_key = self.get_cache_key(symbol)
                        expired_data = cache.get(cache_key, None)
                        if expired_data:
                            logger.info(f"Using expired Redis data for {symbol}")
                            return json.loads(expired_data)
                    except (redis.exceptions.RedisError, json.JSONDecodeError, Exception) as e:
                        logger.warning(f"Failed to get expired data from Redis for {symbol}: {str(e)}")
                
                # Then try memory cache
                memory_cached_data = self._get_from_memory_cache(symbol)
                if memory_cached_data:
                    logger.info(f"Using memory cached data for {symbol}")
                    return memory_cached_data
            
            # Return default data if all else fails
            default_data = self._get_default_stock_data(symbol)
            # Save to memory cache so we don't repeatedly hit the API
            self._set_in_memory_cache(symbol, default_data)
            return default_data
    
    # Add a cache decorator to prevent duplicate calls to the same symbols
    @lru_cache(maxsize=100)
    def refresh_multiple_stocks_cached(self, symbols_tuple):
        """Cached version to prevent duplicate API calls for the same symbols"""
        symbols = list(symbols_tuple)
        results = {}
        
        # First try to get from caches without API calls
        for symbol in symbols:
            symbol = symbol.upper()
            # Skip if already being fetched
            if symbol in self.currently_fetching:
                logger.info(f"Skipping {symbol} as it's already being fetched")
                results[symbol] = False
                continue
                
            data = None
            # Try Redis first
            if self.redis_available:
                try:
                    cache_key = self.get_cache_key(symbol)
                    cached_data = cache.get(cache_key)
                    if cached_data:
                        logger.debug(f"Using Redis cached data for {symbol}")
                        data = json.loads(cached_data)
                        results[symbol] = True
                        continue
                except Exception:
                    pass
                    
            # Then try memory cache
            memory_data = self._get_from_memory_cache(symbol)
            if memory_data:
                logger.debug(f"Using memory cached data for {symbol}")
                results[symbol] = True
                continue
                
            # If not cached, we need to fetch
            try:
                self.currently_fetching.add(symbol)
                self.refresh_stock_data(symbol)
                results[symbol] = True
            except Exception as e:
                logger.error(f"Error refreshing {symbol}: {str(e)}")
                results[symbol] = False
            finally:
                self.currently_fetching.discard(symbol)
                
        return results
        
    def refresh_multiple_stocks(self, symbols):
        """
        Refresh data for multiple stocks
        Returns a dictionary mapping symbols to success/failure status
        """
        # Convert list to tuple for caching
        return self.refresh_multiple_stocks_cached(tuple(symbols))
    
    def clear_cache(self, symbol=None):
        """
        Clear cache for a specific symbol or all symbols
        """
        # Clear memory cache
        if symbol:
            symbol = symbol.upper()
            if symbol in MEMORY_CACHE:
                del MEMORY_CACHE[symbol]
                if symbol in MEMORY_CACHE_TIMESTAMPS:
                    del MEMORY_CACHE_TIMESTAMPS[symbol]
                logger.info(f"Cleared memory cache for {symbol}")
        else:
            MEMORY_CACHE.clear()
            MEMORY_CACHE_TIMESTAMPS.clear()
            logger.info("Cleared all memory cache")
            
        # Clear Redis cache if available
        if self.redis_available:
            try:
                if symbol:
                    symbol = symbol.upper()
                    cache.delete(self.get_cache_key(symbol))
                    cache.delete(self.get_cache_key(symbol, 'price'))
                    logger.info(f"Cleared Redis cache for {symbol}")
                else:
                    # This is a simplistic approach. In production, you'd want a more targeted way
                    # to clear only stock-related cache entries
                    cache.clear()
                    logger.info("Cleared all Redis cache")
            except (redis.exceptions.RedisError, Exception) as e:
                logger.warning(f"Error clearing Redis cache: {str(e)}")
                
        # Clear the function cache
        self.refresh_multiple_stocks_cached.cache_clear() 