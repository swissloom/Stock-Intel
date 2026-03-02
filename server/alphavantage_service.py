import requests
import time
from datetime import datetime

# Get your free API key from: https://www.alphavantage.co/support/#api-key
ALPHA_VANTAGE_API_KEY = 'RCRJKNJ6K490DDML'

BASE_URL = 'https://www.alphavantage.co/query'

def get_quote(symbol):
    """Get real-time quote for a symbol"""
    try:
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': symbol,
            'apikey': ALPHA_VANTAGE_API_KEY
        }
        
        response = requests.get(BASE_URL, params=params)
        data = response.json()
        
        if 'Global Quote' in data and data['Global Quote']:
            quote = data['Global Quote']
            return {
                'symbol': quote.get('01. symbol', symbol),
                'price': float(quote.get('05. price', 0)),
                'change': float(quote.get('09. change', 0)),
                'changePercent': float(quote.get('10. change percent', '0').replace('%', '')),
                'volume': int(quote.get('06. volume', 0)),
                'latestTradingDay': quote.get('07. latest trading day', ''),
                'previousClose': float(quote.get('08. previous close', 0)),
                'open': float(quote.get('02. open', 0)),
                'high': float(quote.get('03. high', 0)),
                'low': float(quote.get('04. low', 0)),
            }
        return None
    except Exception as e:
        print(f"Error fetching quote for {symbol}: {str(e)}")
        return None

def get_company_overview(symbol):
    """Get company fundamentals"""
    try:
        params = {
            'function': 'OVERVIEW',
            'symbol': symbol,
            'apikey': ALPHA_VANTAGE_API_KEY
        }
        
        response = requests.get(BASE_URL, params=params)
        data = response.json()
        
        if data and 'Symbol' in data:
            return {
                'name': data.get('Name', symbol),
                'sector': data.get('Sector', 'Unknown'),
                'marketCap': float(data.get('MarketCapitalization', 0)) / 1e9,
                'peRatio': float(data.get('PERatio', 0)) if data.get('PERatio') != 'None' else None,
                'pegRatio': float(data.get('PEGRatio', 0)) if data.get('PEGRatio') != 'None' else None,
                'beta': float(data.get('Beta', 1.0)) if data.get('Beta') != 'None' else 1.0,
                'dividendYield': float(data.get('DividendYield', 0)) * 100 if data.get('DividendYield') != 'None' else 0,
                'eps': float(data.get('EPS', 0)) if data.get('EPS') != 'None' else 0,
                'profitMargin': float(data.get('ProfitMargin', 0)) * 100 if data.get('ProfitMargin') != 'None' else 0,
                'operatingMargin': float(data.get('OperatingMarginTTM', 0)) * 100 if data.get('OperatingMarginTTM') != 'None' else 0,
                'returnOnEquity': float(data.get('ReturnOnEquityTTM', 0)) * 100 if data.get('ReturnOnEquityTTM') != 'None' else 0,
                'revenueGrowth': float(data.get('QuarterlyRevenueGrowthYOY', 0)) * 100 if data.get('QuarterlyRevenueGrowthYOY') != 'None' else 0,
                'earningsGrowth': float(data.get('QuarterlyEarningsGrowthYOY', 0)) * 100 if data.get('QuarterlyEarningsGrowthYOY') != 'None' else 0,
                'bookValue': float(data.get('BookValue', 0)) if data.get('BookValue') != 'None' else 0,
                '52WeekHigh': float(data.get('52WeekHigh', 0)) if data.get('52WeekHigh') != 'None' else 0,
                '52WeekLow': float(data.get('52WeekLow', 0)) if data.get('52WeekLow') != 'None' else 0,
            }
        return None
    except Exception as e:
        print(f"Error fetching overview for {symbol}: {str(e)}")
        return None

def get_historical_data(symbol, outputsize='compact'):
    """Get historical daily data (compact = 100 days, full = 20 years)"""
    try:
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': symbol,
            'outputsize': outputsize,
            'apikey': ALPHA_VANTAGE_API_KEY
        }
        
        response = requests.get(BASE_URL, params=params)
        data = response.json()
        
        if 'Time Series (Daily)' in data:
            time_series = data['Time Series (Daily)']
            history = []
            
            for date, values in sorted(time_series.items())[-30:]:  # Last 30 days
                history.append(float(values['4. close']))
            
            return history
        return []
    except Exception as e:
        print(f"Error fetching historical data for {symbol}: {str(e)}")
        return []

def get_stock_data_alphavantage(symbol):
    """Get complete stock data from Alpha Vantage"""
    quote = get_quote(symbol)
    
    if not quote:
        return None
    
    # Add small delay to respect rate limits (5 calls/minute for free tier)
    time.sleep(12)  # 12 seconds = 5 calls per minute
    
    overview = get_company_overview(symbol)
    
    if not overview:
        overview = {
            'name': symbol,
            'sector': 'Unknown',
            'marketCap': 0,
            'pegRatio': 1.5,
            'beta': 1.0,
        }
    
    # Calculate price change over 6 months (approximate from available data)
    price_change_6m = quote['changePercent'] * 30  # Rough estimate
    
    return {
        'ticker': symbol,
        'name': overview['name'],
        'price': quote['price'],
        'marketCap': overview['marketCap'],
        'pegRatio': overview.get('pegRatio', 1.5) or 1.5,
        'priceChange6m': price_change_6m,
        'priceHistory': get_historical_data(symbol),
        'sector': overview['sector'],
        'beta': overview.get('beta', 1.0),
        'forwardPE': overview.get('peRatio'),
        'trailingPE': overview.get('peRatio'),
        'ma200': None,  # Would need additional API call
        'ma50': None,
        'rsi': None,
        'institutionalOwnership': 0,
        'analystRating': None,
        'priceToBook': quote['price'] / overview.get('bookValue', 1) if overview.get('bookValue') else None,
        'debtToEquity': 0,
        'returnOnEquity': overview.get('returnOnEquity', 0),
        'profitMargin': overview.get('profitMargin', 0),
        'operatingMargin': overview.get('operatingMargin', 0),
        'freeCashFlow': 0,
        'revenueGrowth': overview.get('revenueGrowth', 0),
        'earningsGrowth': overview.get('earningsGrowth', 0),
        'dividendYield': overview.get('dividendYield', 0),
        'shortRatio': 0,
        'volume': quote['volume'],
        'avgVolume': quote['volume'],
    }
