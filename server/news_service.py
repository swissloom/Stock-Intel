import requests
from datetime import datetime, timedelta

def get_stock_news(ticker, limit=10):
    """Fetch news for a specific stock using Yahoo Finance"""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        news = stock.news
        
        if not news:
            return []
        
        formatted_news = []
        for item in news[:limit]:
            formatted_news.append({
                'title': item.get('title', ''),
                'publisher': item.get('publisher', 'Unknown'),
                'link': item.get('link', ''),
                'publishedAt': datetime.fromtimestamp(item.get('providerPublishTime', 0)).isoformat(),
                'thumbnail': item.get('thumbnail', {}).get('resolutions', [{}])[0].get('url', ''),
            })
        
        return formatted_news
    except Exception as e:
        print(f"Error fetching news for {ticker}: {str(e)}")
        return []

def get_market_news(limit=20):
    """Fetch general market news"""
    try:
        import yfinance as yf
        # Use SPY as proxy for market news
        spy = yf.Ticker('SPY')
        news = spy.news
        
        if not news:
            return []
        
        formatted_news = []
        for item in news[:limit]:
            formatted_news.append({
                'title': item.get('title', ''),
                'publisher': item.get('publisher', 'Unknown'),
                'link': item.get('link', ''),
                'publishedAt': datetime.fromtimestamp(item.get('providerPublishTime', 0)).isoformat(),
                'thumbnail': item.get('thumbnail', {}).get('resolutions', [{}])[0].get('url', ''),
            })
        
        return formatted_news
    except Exception as e:
        print(f"Error fetching market news: {str(e)}")
        return []
