# Stock Price API Setup Guide

## Current Issue
yfinance is unofficial and can have price discrepancies due to scraping delays and rate limiting.

## Recommended Solution: Alpha Vantage

### Why Alpha Vantage?
- ✅ **Most accurate free option**
- ✅ Real-time quotes (15-min delay on free tier)
- ✅ Comprehensive fundamentals
- ✅ 25 API calls per day (free)
- ✅ Official API with reliable data
- ✅ No credit card required

### Setup Instructions

1. **Get Your Free API Key**
   - Visit: https://www.alphavantage.co/support/#api-key
   - Enter your email
   - Get instant API key (no verification needed)

2. **Update the Configuration**
   - Open `server/alphavantage_service.py`
   - Replace `ALPHA_VANTAGE_API_KEY = 'demo'` with your actual key
   - Example: `ALPHA_VANTAGE_API_KEY = 'YOUR_KEY_HERE'`

3. **Switch to Alpha Vantage**
   - The server is already configured to use Alpha Vantage
   - Just restart: `python3 server.py`

### Rate Limits
- **Free Tier**: 25 requests/day, 5 requests/minute
- **Paid Tier**: $49.99/month for 75 requests/minute

### Alternative APIs (If You Need More Calls)

#### Finnhub (Best for High Frequency)
```python
# Free: 60 calls/minute
# Signup: https://finnhub.io/register
API_KEY = 'your_finnhub_key'
url = f'https://finnhub.io/api/v1/quote?symbol={ticker}&token={API_KEY}'
```

#### Polygon.io (Professional Grade)
```python
# Free: 5 calls/minute
# Signup: https://polygon.io/
API_KEY = 'your_polygon_key'
url = f'https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?apiKey={API_KEY}'
```

#### IEX Cloud (Clean Data)
```python
# Free: 50,000 messages/month
# Signup: https://iexcloud.io/
API_KEY = 'your_iex_key'
url = f'https://cloud.iexapis.com/stable/stock/{ticker}/quote?token={API_KEY}'
```

### Comparison Table

| API | Free Calls | Accuracy | Best For |
|-----|-----------|----------|----------|
| Alpha Vantage | 25/day | ⭐⭐⭐⭐⭐ | Fundamentals + Price |
| Finnhub | 60/min | ⭐⭐⭐⭐ | Real-time quotes |
| Polygon.io | 5/min | ⭐⭐⭐⭐⭐ | Professional trading |
| IEX Cloud | 50k/month | ⭐⭐⭐⭐ | High volume |
| yfinance | Unlimited | ⭐⭐⭐ | Quick prototyping |

### Current Implementation
The dashboard now supports both:
1. **yfinance** (default, unlimited but less accurate)
2. **Alpha Vantage** (optional, more accurate with API key)

To switch, just add your Alpha Vantage API key and the system will automatically use it.
