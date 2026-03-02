# Yahoo Finance Backend Server

This Python Flask server fetches real-time stock data from Yahoo Finance using the yfinance library.

## Setup

1. Install Python 3.8 or higher
2. Install dependencies:
```bash
cd server
pip install -r requirements.txt
```

## Run the Server

```bash
python server.py
```

The server will start on http://localhost:5000

## API Endpoint

- `GET /api/stocks` - Returns comprehensive real-time data for all configured stocks

## Data Included

### Price & Valuation
- Current price, market cap, P/E ratios, PEG ratio, price-to-book

### Technical Indicators  
- 50-day and 200-day moving averages
- RSI (Relative Strength Index)
- Beta, volume metrics

### Institutional Metrics (What Top Firms Use)
- Institutional ownership percentage
- Analyst ratings (Strong Buy/Buy/Hold/Sell/Strong Sell)
- Short ratio
- Volume analysis

### Financial Health
- Return on Equity (ROE)
- Profit margins and operating margins
- Debt-to-equity ratio
- Free cash flow

### Growth Metrics
- Revenue growth
- Earnings growth
- Dividend yield
