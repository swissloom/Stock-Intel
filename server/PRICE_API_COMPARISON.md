# Stock Price API Comparison

## The Problem
- **yfinance**: Unofficial scraper, often has stale/incorrect prices
- **Alpha Vantage**: Only 25 calls/day on free tier, too limiting
- **TradingView**: No public API for price data (only charting widgets)

## Best Solutions for Accurate Real-Time Prices

### 1. Finnhub ⭐ RECOMMENDED
**Why it's best:**
- ✅ **60 API calls per minute** (free tier)
- ✅ **Real-time quotes** with no delay
- ✅ **Most accurate free option**
- ✅ Easy to set up (2 minutes)
- ✅ Comprehensive data (prices, fundamentals, news)

**Setup:**
1. Register: https://finnhub.io/register
2. Get instant API key
3. Update `server/finnhub_service.py`: `FINNHUB_API_KEY = 'your_key'`
4. Restart server

**Free Tier:**
- 60 calls/minute
- Real-time US stock quotes
- Company profiles
- Basic financials
- News

**Paid Tier:** $59.99/month for more calls

---

### 2. Polygon.io (Professional Grade)
**Pros:**
- ✅ Most accurate data (used by professionals)
- ✅ Real-time market data
- ✅ Comprehensive historical data

**Cons:**
- ❌ Only 5 calls/minute (free tier)
- ❌ More complex API

**Free Tier:** 5 calls/minute
**Paid Tier:** $29/month for 100 calls/minute

---

### 3. IEX Cloud (Clean & Simple)
**Pros:**
- ✅ 50,000 messages/month (free)
- ✅ Clean, well-documented API
- ✅ Real-time IEX exchange data

**Cons:**
- ❌ Only IEX exchange data (not all exchanges)

**Free Tier:** 50,000 messages/month
**Paid Tier:** $9/month for more

---

### 4. Twelve Data (Good Balance)
**Pros:**
- ✅ 800 API calls/day (free)
- ✅ Multiple asset classes
- ✅ Good documentation

**Cons:**
- ❌ 8 calls/minute rate limit

**Free Tier:** 800 calls/day
**Paid Tier:** $29/month

---

## Recommendation

**For your dashboard: Use Finnhub**

Reasons:
1. **60 calls/minute** = Can load 50+ stocks quickly
2. **Real-time prices** = Accurate data
3. **Free tier is generous** = No cost
4. **Easy integration** = Already coded for you

## Current Implementation

The server now supports:
1. **yfinance** (default, unlimited but inaccurate)
2. **Alpha Vantage** (accurate but only 25/day)
3. **Finnhub** (accurate + 60/minute) ← **USE THIS**

To switch to Finnhub:
1. Get API key: https://finnhub.io/register
2. Update `server/finnhub_service.py`
3. Update `server/server.py` to use Finnhub instead of Alpha Vantage
4. Restart server

## Price Accuracy Comparison

| API | Accuracy | Delay | Free Calls |
|-----|----------|-------|------------|
| Finnhub | ⭐⭐⭐⭐⭐ | Real-time | 60/min |
| Polygon.io | ⭐⭐⭐⭐⭐ | Real-time | 5/min |
| IEX Cloud | ⭐⭐⭐⭐ | Real-time | 50k/month |
| Alpha Vantage | ⭐⭐⭐⭐ | 15-min delay | 25/day |
| yfinance | ⭐⭐⭐ | Variable | Unlimited |
