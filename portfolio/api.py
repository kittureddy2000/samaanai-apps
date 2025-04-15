import requests
import logging
import json
import time
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from datetime import timedelta

from .models import Stock

logger = logging.getLogger(__name__)

# Alpha Vantage API integration
ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"


class StockAPIError(Exception):
    """Custom exception for stock API errors"""
    pass


def get_api_key():
    """Get the Alpha Vantage API key from settings"""
    api_key = getattr(settings, 'ALPHA_VANTAGE_API_KEY', None)
    
    # Add more detailed logging for API key retrieval
    if not api_key:
        logger.error("CRITICAL: Alpha Vantage API key is not configured in settings")
        raise StockAPIError("Alpha Vantage API key is not configured in settings")
    
    logger.info(f"Using Alpha Vantage API key: {api_key[:4]}...{api_key[-4:] if len(api_key) > 8 else ''}")
    return api_key


def fetch_stock_data(symbol):
    """
    Fetch current stock data from Alpha Vantage API
    Returns a tuple (price, company_name, additional_data)
    where additional_data is a dictionary containing extended stock information
    """
    logger.info(f"Fetching stock data for symbol: {symbol}")
    
    try:
        api_key = get_api_key()
        logger.info(f"Using API key: {api_key[:4]}...{api_key[-4:] if len(api_key) > 8 else ''}")
    except Exception as e:
        logger.error(f"Failed to get API key: {str(e)}")
        raise StockAPIError(f"API key error: {str(e)}")
    
    # First, get the quote
    quote_params = {
        'function': 'GLOBAL_QUOTE',
        'symbol': symbol,
        'apikey': api_key
    }
    
    logger.debug(f"Request parameters for quote: {json.dumps({k: v if k != 'apikey' else '***' for k, v in quote_params.items()})}")
    
    try:
        logger.info(f"Making request to Alpha Vantage for {symbol} quote data")
        
        # Print the full URL for debugging (hide the API key)
        full_url = ALPHA_VANTAGE_BASE_URL + "?" + "&".join([f"{k}={'***' if k == 'apikey' else v}" for k, v in quote_params.items()])
        logger.debug(f"Request URL: {full_url}")
        
        response = None
        try:
            response = requests.get(ALPHA_VANTAGE_BASE_URL, params=quote_params, timeout=15)
            logger.info(f"Response status code: {response.status_code}")
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout for {symbol}")
            raise StockAPIError(f"Request timeout for {symbol}")
        except requests.exceptions.ConnectionError as ce:
            logger.error(f"Connection error for {symbol}: {str(ce)}")
            raise StockAPIError(f"Connection error: {str(ce)}")
        
        if response is None:
            logger.error(f"No response received for {symbol}")
            raise StockAPIError(f"No response received for {symbol}")
        
        # Log detailed response info
        logger.debug(f"Response headers: {dict(response.headers)}")
        
        # Log raw response text before trying to parse as JSON
        try:
            raw_text = response.text[:500]  # First 500 chars in case it's huge
            logger.debug(f"Raw response text: {raw_text}")
        except Exception as e:
            logger.warning(f"Could not get raw response text: {str(e)}")
        
        try:
            response.raise_for_status()  # Raises an exception for HTTP errors
        except requests.exceptions.HTTPError as he:
            logger.error(f"HTTP error for {symbol}: {str(he)}")
            raise StockAPIError(f"HTTP error: {str(he)}")
        
        # Parse JSON response
        try:
            data = response.json()
        except ValueError as ve:
            logger.error(f"Invalid JSON response for {symbol}: {str(ve)}")
            raise StockAPIError(f"Invalid JSON response: {str(ve)}")
        
        logger.debug(f"Quote response data: {json.dumps(data)}")
        
        # Check for API error messages
        if "Error Message" in data:
            error_msg = f"API Error for {symbol}: {data['Error Message']}"
            logger.error(error_msg)
            raise StockAPIError(error_msg)
        
        # Check for API rate limit messages
        if "Note" in data and "API call frequency" in data["Note"]:
            logger.warning(f"Alpha Vantage rate limit warning: {data['Note']}")
        
        # Extract price information
        if "Global Quote" in data and data["Global Quote"]:
            quote_data = data["Global Quote"]
            
            # Check if quote data is empty (sometimes happens with valid requests but invalid symbols)
            if not quote_data or all(not v for v in quote_data.values()):
                logger.warning(f"Empty quote data received for {symbol}")
                return Decimal("0.00"), symbol, {}
                
            price_str = quote_data.get("05. price", "0.00")
            logger.info(f"Retrieved price for {symbol}: {price_str}")
            price = Decimal(price_str)
            
            # Extract previous close for day change calculation
            prev_close_str = quote_data.get("08. previous close", "0.00")
            prev_close = Decimal(prev_close_str)
            
            # Calculate day's change
            day_change = price - prev_close
            day_change_percentage = Decimal("0.00")
            if prev_close > 0:
                day_change_percentage = (day_change / prev_close) * 100
        else:
            logger.warning(f"No price data found for {symbol}. Response: {json.dumps(data)}")
            price = Decimal("0.00")
            day_change = Decimal("0.00")
            day_change_percentage = Decimal("0.00")
        
        # Now get company overview for the name
        # To prevent hitting API rate limits, sleep briefly
        time.sleep(1.0)  # Increased sleep time to be safer with rate limits
        
        overview_params = {
            'function': 'OVERVIEW',
            'symbol': symbol,
            'apikey': api_key
        }
        
        logger.debug(f"Request parameters for overview: {json.dumps({k: v if k != 'apikey' else '***' for k, v in overview_params.items()})}")
        
        logger.info(f"Making request to Alpha Vantage for {symbol} company overview")
        response = requests.get(ALPHA_VANTAGE_BASE_URL, params=overview_params)
        
        # Log response info
        logger.info(f"Overview response status code: {response.status_code}")
        
        response.raise_for_status()
        
        overview_data = response.json()
        logger.debug(f"Overview response data: {json.dumps(overview_data)}")
        
        # Initialize additional data dictionary
        additional_data = {
            'day_change': day_change,
            'day_change_percentage': day_change_percentage,
            'fifty_two_week_high': None,
            'fifty_two_week_low': None,
            'pe_ratio': None,
            'dividend_yield': None,
        }
        
        # Check if overview data is empty (happens with valid API key but invalid symbol)
        if not overview_data or (isinstance(overview_data, dict) and not overview_data):
            logger.warning(f"Empty overview data received for {symbol}")
            company_name = symbol
        else:
            # Extract company name
            if "Name" in overview_data:
                company_name = overview_data["Name"]
                logger.info(f"Retrieved company name for {symbol}: {company_name}")
            else:
                logger.warning(f"No company name found for {symbol}. Using symbol as fallback.")
                company_name = symbol  # Use symbol as fallback
            
            # Extract additional data
            try:
                if "52WeekHigh" in overview_data:
                    additional_data['fifty_two_week_high'] = Decimal(overview_data["52WeekHigh"])
                
                if "52WeekLow" in overview_data:
                    additional_data['fifty_two_week_low'] = Decimal(overview_data["52WeekLow"])
                
                if "PERatio" in overview_data and overview_data["PERatio"] != "None":
                    additional_data['pe_ratio'] = Decimal(overview_data["PERatio"])
                
                if "DividendYield" in overview_data and overview_data["DividendYield"] != "None":
                    # DividendYield is often given as a decimal (e.g., 0.0291 for 2.91%)
                    dividend_yield = Decimal(overview_data["DividendYield"])
                    additional_data['dividend_yield'] = dividend_yield * 100  # Convert to percentage
                
                logger.info(f"Retrieved additional data for {symbol}: {additional_data}")
            except (ValueError, TypeError, KeyError) as e:
                logger.warning(f"Error parsing additional data for {symbol}: {str(e)}")
        
        return price, company_name, additional_data
    
    except requests.exceptions.RequestException as e:
        error_msg = f"API request error for {symbol}: {str(e)}"
        logger.error(error_msg)
        # For connection issues, provide more details
        if isinstance(e, requests.exceptions.ConnectionError):
            logger.error(f"Connection error details: {str(e)}")
        raise StockAPIError(error_msg)
    except (KeyError, ValueError) as e:
        error_msg = f"Error parsing data for {symbol}: {str(e)}"
        logger.error(error_msg)
        raise StockAPIError(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error fetching data for {symbol}: {str(e)}"
        logger.error(error_msg, exc_info=True)  # Include stack trace
        raise StockAPIError(error_msg)


def update_stock_info(stock):
    """
    Update stock information from the API
    Returns True if successful, False otherwise
    """
    logger.info(f"Updating stock info for {stock.symbol}")
    try:
        price, company_name, additional_data = fetch_stock_data(stock.symbol)
        
        # Update only core data
        if not stock.name and company_name:
            stock.name = company_name
        
        # Update day change
        stock.day_change = additional_data.get('day_change', Decimal('0.00'))
        stock.day_change_percentage = additional_data.get('day_change_percentage', Decimal('0.00'))
        
        # Update additional stock data
        if 'fifty_two_week_high' in additional_data and additional_data['fifty_two_week_high']:
            stock.fifty_two_week_high = additional_data['fifty_two_week_high']
        
        if 'fifty_two_week_low' in additional_data and additional_data['fifty_two_week_low']:
            stock.fifty_two_week_low = additional_data['fifty_two_week_low']
        
        if 'pe_ratio' in additional_data and additional_data['pe_ratio']:
            stock.pe_ratio = additional_data['pe_ratio']
        
        if 'dividend_yield' in additional_data and additional_data['dividend_yield']:
            stock.dividend_yield = additional_data['dividend_yield']
        
        # Update price
        stock.update_price(price)
        
        # Return full additional data
        return True, additional_data
        
    except Exception as e:
        # Error handling
        logger.error(f"Error updating stock {stock.symbol}: {str(e)}")
        return False, {}

# New Cloud Tasks handler endpoints

@csrf_exempt
@require_POST
def refresh_stocks(request):
    """
    API endpoint to handle refresh stock data requests from Cloud Tasks
    """
    try:
        # Parse the request body
        data = json.loads(request.body)
        symbols = data.get('symbols', None)
        
        logger.info(f"Processing refresh-stocks task: {symbols if symbols else 'all stale'}")
        
        from .services import StockDataService
        stock_service = StockDataService()
        
        if symbols:
            # Update specific symbols
            results = stock_service.refresh_multiple_stocks(symbols)
            updated_count = sum(1 for result in results.values() if result)
            error_count = len(results) - updated_count
        else:
            # Update all stocks with stale data (not updated in the last 15 minutes)
            from .models import Stock
            symbols = list(Stock.objects.values_list('symbol', flat=True))
            results = stock_service.refresh_multiple_stocks(symbols)
            updated_count = sum(1 for result in results.values() if result)
            error_count = len(results) - updated_count
        
        logger.info(f"Stock refresh complete. Updated: {updated_count}, Errors: {error_count}")
        return JsonResponse({
            'status': 'success',
            'updated': updated_count,
            'errors': error_count
        })
        
    except Exception as e:
        logger.error(f"Error in refresh_stocks endpoint: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

@csrf_exempt
@require_POST
def refresh_all_stocks(request):
    """
    API endpoint to handle refresh all stocks request from Cloud Tasks
    """
    try:
        logger.info("Processing refresh-all-stocks task")
        
        # Get all symbols in the database
        from .models import Stock
        symbols = list(Stock.objects.values_list('symbol', flat=True))
        
        from .services import StockDataService
        stock_service = StockDataService()
        results = stock_service.refresh_multiple_stocks(symbols)
        
        updated_count = sum(1 for result in results.values() if result)
        error_count = len(results) - updated_count
        
        logger.info(f"All stocks refresh complete. Updated: {updated_count}, Errors: {error_count}")
        return JsonResponse({
            'status': 'success',
            'updated': updated_count,
            'errors': error_count
        })
        
    except Exception as e:
        logger.error(f"Error in refresh_all_stocks endpoint: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)