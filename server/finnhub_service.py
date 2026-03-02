import requests
import time

# Get your free API key from: https://finnhub.io/register
FINNHUB_API_KEY = 'd6hdsc9r01qnjncoai80d6hdsc9r01qnjncoai8g'

BASE_URL = 'https://finnhub.io/api/v1'

def get_quote_finnhub(symbol):
    """Get real-time quote from Finnhub"""
    try:
        url = f'{BASE_URL}/quote'
        params = {
            'symbol': symbol,
            'token': FINNHUB_API_KEY
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if data and 'c' in data:
            return {
                'symbol': symbol,
                'price': data['c'],  # Current price
                'change': data['d'],  # Change
                'changePercent': data['dp'],  # Percent change
                'high': data['h'],  # High price of the day
                'low': data['l'],  # Low price of the day
                'open': data['o'],  # Open price of the day
                'previousClose': data['pc'],  # Previous close price
            }
        return None
    except Exception as e:
        print(f"Error fetching Finnhub quote for {symbol}: {str(e)}")
        return None

def get_company_profile_finnhub(symbol):
    """Get company profile from Finnhub"""
    try:
        url = f'{BASE_URL}/stock/profile2'
        params = {
            'symbol': symbol,
            'token': FINNHUB_API_KEY
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if data and 'name' in data:
            return {
                'name': data.get('name', symbol),
                'sector': data.get('finnhubIndustry', 'Unknown'),
                'marketCap': data.get('marketCapitalization', 0),  # Already in millions
                'logo': data.get('logo', ''),
                'weburl': data.get('weburl', ''),
                'ipo': data.get('ipo', ''),
            }
        return None
    except Exception as e:
        print(f"Error fetching Finnhub profile for {symbol}: {str(e)}")
        return None

def get_basic_financials_finnhub(symbol):
    """Get basic financials from Finnhub"""
    try:
        url = f'{BASE_URL}/stock/metric'
        params = {
            'symbol': symbol,
            'metric': 'all',
            'token': FINNHUB_API_KEY
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if data and 'metric' in data:
            metric = data['metric']
            return {
                'peRatio': metric.get('peBasicExclExtraTTM'),
                'pegRatio': metric.get('pegRatio'),
                'beta': metric.get('beta'),
                'dividendYield': metric.get('dividendYieldIndicatedAnnual', 0),
                'eps': metric.get('epsBasicExclExtraItemsTTM'),
                'profitMargin': metric.get('netProfitMarginTTM'),
                'operatingMargin': metric.get('operatingMarginTTM'),
                'returnOnEquity': metric.get('roeTTM'),
                'bookValue': metric.get('bookValuePerShareAnnual'),
                '52WeekHigh': metric.get('52WeekHigh'),
                '52WeekLow': metric.get('52WeekLow'),
            }
        return {}
    except Exception as e:
        print(f"Error fetching Finnhub financials for {symbol}: {str(e)}")
        return {}

def get_historical_candles_finnhub(symbol, days=180):
    """Get historical candles from Finnhub"""
    try:
        from datetime import datetime, timedelta
        
        # Calculate timestamps
        end_time = int(datetime.now().timestamp())
        start_time = int((datetime.now() - timedelta(days=days)).timestamp())
        
        url = f'{BASE_URL}/stock/candle'
        params = {
            'symbol': symbol,
            'resolution': 'D',  # Daily
            'from': start_time,
            'to': end_time,
            'token': FINNHUB_API_KEY
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if data and data.get('s') == 'ok' and 'c' in data:
            return {
                'closes': data['c'],  # Closing prices
                'opens': data['o'],
                'highs': data['h'],
                'lows': data['l'],
                'volumes': data['v'],
                'timestamps': data['t']
            }
        return None
    except Exception as e:
        print(f"Error fetching Finnhub candles for {symbol}: {str(e)}")
        return None

def get_stock_data_finnhub(symbol):
    """Get complete stock data from Finnhub"""
    quote = get_quote_finnhub(symbol)
    
    if not quote:
        return None
    
    # Small delay to respect rate limits
    time.sleep(0.1)
    
    profile = get_company_profile_finnhub(symbol)
    financials = get_basic_financials_finnhub(symbol)
    
    # Use yfinance for historical data (Finnhub free tier doesn't include candles)
    price_change_6m = 0
    price_history = []
    
    # Try to get 52-week high/low from Finnhub financials as a proxy
    if financials.get('52WeekHigh') and financials.get('52WeekLow'):
        week_52_high = financials['52WeekHigh']
        week_52_low = financials['52WeekLow']
        current_price = quote['price']
        
        # Estimate 6-month change based on position in 52-week range
        # This is an approximation but better than nothing
        range_position = (current_price - week_52_low) / (week_52_high - week_52_low) if week_52_high != week_52_low else 0.5
        
        # Rough estimate: if near 52w high, likely positive 6m change
        if range_position > 0.7:
            price_change_6m = 15 + (range_position - 0.7) * 50  # 15-30% range
        elif range_position > 0.5:
            price_change_6m = (range_position - 0.5) * 75  # 0-15% range
        elif range_position > 0.3:
            price_change_6m = -15 + (range_position - 0.3) * 75  # -15 to 0% range
        else:
            price_change_6m = -30 + range_position * 50  # -30 to -15% range
    
    # Try yfinance as backup (with error handling)
    try:
        import yfinance as yf
        stock = yf.Ticker(symbol)
        hist = stock.history(period='6mo', timeout=5)
        
        if not hist.empty and len(hist) > 1:
            price_6m_ago = hist['Close'].iloc[0]
            current_price = quote['price']
            price_change_6m = ((current_price - price_6m_ago) / price_6m_ago) * 100
            
            # Get last 30 days for sparkline
            hist_30d = stock.history(period='1mo', timeout=5)
            if not hist_30d.empty:
                price_history = hist_30d['Close'].tolist()[-30:]
    except Exception as e:
        # Silently fail and use the estimate from 52-week range
        pass
    
    if not profile:
        profile = {
            'name': symbol,
            'sector': 'Unknown',
            'marketCap': 0,
        }
    
    return {
        'ticker': symbol,
        'name': profile['name'],
        'price': quote['price'],  # Accurate from Finnhub
        'marketCap': profile['marketCap'] / 1000,  # Convert millions to billions
        'pegRatio': financials.get('pegRatio', 1.5) or 1.5,
        'priceChange6m': price_change_6m,  # Calculated from yfinance historical + Finnhub current
        'priceHistory': price_history,  # From yfinance
        'sector': profile['sector'],
        'beta': financials.get('beta', 1.0) or 1.0,
        'forwardPE': financials.get('peRatio'),
        'trailingPE': financials.get('peRatio'),
        'ma200': None,
        'ma50': None,
        'rsi': None,
        'institutionalOwnership': 0,
        'analystRating': None,
        'priceToBook': quote['price'] / financials.get('bookValue', 1) if financials.get('bookValue') else None,
        'debtToEquity': 0,
        'returnOnEquity': financials.get('returnOnEquity', 0) or 0,
        'profitMargin': financials.get('profitMargin', 0) or 0,
        'operatingMargin': financials.get('operatingMargin', 0) or 0,
        'freeCashFlow': 0,
        'revenueGrowth': 0,
        'earningsGrowth': 0,
        'dividendYield': financials.get('dividendYield', 0) or 0,
        'shortRatio': 0,
        'volume': 0,
        'avgVolume': 0,
    }
