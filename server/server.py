from flask import Flask, jsonify, send_file
from flask_cors import CORS
import yfinance as yf
from datetime import datetime, timedelta
import pandas as pd
import time
import io
from news_service import get_stock_news, get_market_news
from analytics_service import get_advanced_analytics, backtest_strategy
from alphavantage_service import get_stock_data_alphavantage, ALPHA_VANTAGE_API_KEY
from finnhub_service import get_stock_data_finnhub, FINNHUB_API_KEY

app = Flask(__name__)
CORS(app)

# Choose data source based on API key availability
USE_FINNHUB = FINNHUB_API_KEY != 'demo'
USE_ALPHA_VANTAGE = ALPHA_VANTAGE_API_KEY != 'demo' and not USE_FINNHUB

def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index"""
    if len(prices) < period:
        return None
    
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else None

@app.route('/api/stocks', methods=['GET'])
def get_stocks():
    # Reduced list to avoid rate limiting - focus on most popular stocks
    tickers = [
        # Technology
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'NFLX', 'ADBE',
        'ORCL', 'INTC', 'AMD', 'QCOM', 'AVGO', 'CSCO', 'SHOP',
        # Finance
        'JPM', 'BAC', 'WFC', 'GS', 'V', 'MA', 'PYPL',
        # Consumer
        'WMT', 'COST', 'HD', 'TGT', 'NKE', 'SBUX', 'MCD', 'DIS',
        'PG', 'KO', 'PEP',
        # Healthcare
        'UNH', 'JNJ', 'LLY', 'PFE', 'ABBV',
        # Energy
        'XOM', 'CVX',
        # ETFs
        'SPY', 'QQQ', 'IWM', 'DIA', 'VOO',
        # Other
        'BRK-B'
    ]
    
    stocks_data = []
    
    if USE_FINNHUB:
        print("Using Finnhub API for accurate real-time prices...")
        # Use Finnhub for most accurate real-time data
        for ticker in tickers:
            data = get_stock_data_finnhub(ticker)
            if data:
                stocks_data.append(data)
            time.sleep(0.1)  # Small delay to respect rate limits
        return jsonify(stocks_data)
    elif USE_ALPHA_VANTAGE:
        print("Using Alpha Vantage API for accurate prices...")
        # Use Alpha Vantage for more accurate data
        for ticker in tickers[:10]:  # Limit to 10 stocks due to rate limits
            data = get_stock_data_alphavantage(ticker)
            if data:
                stocks_data.append(data)
        return jsonify(stocks_data)
    else:
        print("Using yfinance (may have discrepancies). Get Finnhub or Alpha Vantage API key for accurate prices.")
        # Fall back to yfinance
        for i, ticker in enumerate(tickers):
            # Add delay every 5 stocks to avoid rate limiting
            if i > 0 and i % 5 == 0:
                time.sleep(1)
            
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                hist = stock.history(period='6mo')
                
                if hist.empty or 'currentPrice' not in info:
                    continue
                
                # Calculate 6-month price change
                if len(hist) > 0:
                    price_6m_ago = hist['Close'].iloc[0]
                    current_price = info.get('currentPrice', hist['Close'].iloc[-1])
                    price_change_6m = ((current_price - price_6m_ago) / price_6m_ago) * 100
                else:
                    price_change_6m = 0
                
                # Get last 30 days for sparkline
                hist_30d = stock.history(period='1mo')
                price_history = hist_30d['Close'].tolist()[-30:] if not hist_30d.empty else []
                
                # Calculate 200-day moving average
                hist_200d = stock.history(period='1y')
                ma_200 = hist_200d['Close'].rolling(window=200).mean().iloc[-1] if len(hist_200d) >= 200 else None
                
                # Calculate 50-day moving average
                ma_50 = hist_30d['Close'].rolling(window=50).mean().iloc[-1] if len(hist_30d) >= 50 else None
                
                # Calculate RSI (Relative Strength Index)
                rsi = calculate_rsi(hist_30d['Close']) if not hist_30d.empty else None
                
                # Get institutional ownership and insider data
                institutional_holders = stock.institutional_holders
                insider_holders = stock.insider_transactions
                
                institutional_ownership = 0
                if institutional_holders is not None and not institutional_holders.empty:
                    institutional_ownership = (institutional_holders['Shares'].sum() / info.get('sharesOutstanding', 1)) * 100
                
                # Get analyst recommendations
                recommendations = stock.recommendations
                analyst_rating = None
                if recommendations is not None and not recommendations.empty:
                    latest = recommendations.iloc[-1]
                    analyst_rating = {
                        'strongBuy': latest.get('strongBuy', 0),
                        'buy': latest.get('buy', 0),
                        'hold': latest.get('hold', 0),
                        'sell': latest.get('sell', 0),
                        'strongSell': latest.get('strongSell', 0),
                    }
                
                stock_data = {
                    'ticker': ticker,
                    'name': info.get('longName', info.get('shortName', ticker)),
                    'price': info.get('currentPrice', 0),
                    'marketCap': info.get('marketCap', 0) / 1e9,  # Convert to billions
                    'pegRatio': info.get('pegRatio', info.get('trailingPegRatio', 1.5)),
                    'priceChange6m': price_change_6m,
                    'priceHistory': price_history,
                'sector': info.get('sector', 'Unknown'),
                'beta': info.get('beta', 1.0),
                'forwardPE': info.get('forwardPE', 0),
                'trailingPE': info.get('trailingPE', 0),
                'ma200': ma_200,
                'ma50': ma_50,
                'rsi': rsi,
                'institutionalOwnership': institutional_ownership,
                'analystRating': analyst_rating,
                'priceToBook': info.get('priceToBook', 0),
                'debtToEquity': info.get('debtToEquity', 0),
                'returnOnEquity': info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0,
                'profitMargin': info.get('profitMargins', 0) * 100 if info.get('profitMargins') else 0,
                'operatingMargin': info.get('operatingMargins', 0) * 100 if info.get('operatingMargins') else 0,
                'freeCashFlow': info.get('freeCashflow', 0) / 1e9 if info.get('freeCashflow') else 0,
                'revenueGrowth': info.get('revenueGrowth', 0) * 100 if info.get('revenueGrowth') else 0,
                'earningsGrowth': info.get('earningsGrowth', 0) * 100 if info.get('earningsGrowth') else 0,
                'dividendYield': info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0,
                'shortRatio': info.get('shortRatio', 0),
                'volume': info.get('volume', 0),
                'avgVolume': info.get('averageVolume', 0),
            }
                
                # Calculate RSI (Relative Strength Index)
                rsi = calculate_rsi(hist_30d['Close']) if not hist_30d.empty else None
                
                # Get institutional ownership and insider data
                institutional_holders = stock.institutional_holders
                insider_holders = stock.insider_transactions
                
                institutional_ownership = 0
                if institutional_holders is not None and not institutional_holders.empty:
                    institutional_ownership = (institutional_holders['Shares'].sum() / info.get('sharesOutstanding', 1)) * 100
                
                # Get analyst recommendations
                recommendations = stock.recommendations
                analyst_rating = None
                if recommendations is not None and not recommendations.empty:
                    latest = recommendations.iloc[-1]
                    analyst_rating = {
                        'strongBuy': latest.get('strongBuy', 0),
                        'buy': latest.get('buy', 0),
                        'hold': latest.get('hold', 0),
                        'sell': latest.get('sell', 0),
                        'strongSell': latest.get('strongSell', 0),
                    }
                
                stock_data = {
                    'ticker': ticker,
                    'name': info.get('longName', info.get('shortName', ticker)),
                    'price': info.get('currentPrice', 0),
                    'marketCap': info.get('marketCap', 0) / 1e9,  # Convert to billions
                    'pegRatio': info.get('pegRatio', info.get('trailingPegRatio', 1.5)),
                    'priceChange6m': price_change_6m,
                    'priceHistory': price_history,
                    'sector': info.get('sector', 'Unknown'),
                    'beta': info.get('beta', 1.0),
                    'forwardPE': info.get('forwardPE', 0),
                    'trailingPE': info.get('trailingPE', 0),
                    'ma200': ma_200,
                    'ma50': ma_50,
                    'rsi': rsi,
                    'institutionalOwnership': institutional_ownership,
                    'analystRating': analyst_rating,
                    'priceToBook': info.get('priceToBook', 0),
                    'debtToEquity': info.get('debtToEquity', 0),
                    'returnOnEquity': info.get('returnOnEquity', 0) * 100 if info.get('returnOnEquity') else 0,
                    'profitMargin': info.get('profitMargins', 0) * 100 if info.get('profitMargins') else 0,
                    'operatingMargin': info.get('operatingMargins', 0) * 100 if info.get('operatingMargins') else 0,
                    'freeCashFlow': info.get('freeCashflow', 0) / 1e9 if info.get('freeCashflow') else 0,
                    'revenueGrowth': info.get('revenueGrowth', 0) * 100 if info.get('revenueGrowth') else 0,
                    'earningsGrowth': info.get('earningsGrowth', 0) * 100 if info.get('earningsGrowth') else 0,
                    'dividendYield': info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0,
                    'shortRatio': info.get('shortRatio', 0),
                    'volume': info.get('volume', 0),
                    'avgVolume': info.get('averageVolume', 0),
                }
                
                stocks_data.append(stock_data)
                
            except Exception as e:
                print(f"Error fetching {ticker}: {str(e)}")
                continue
        
        return jsonify(stocks_data)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

@app.route('/api/news/<ticker>', methods=['GET'])
def get_news(ticker):
    """Get news for a specific stock"""
    news = get_stock_news(ticker, limit=10)
    return jsonify(news)

@app.route('/api/market-news', methods=['GET'])
def get_market_news_endpoint():
    """Get general market news"""
    news = get_market_news(limit=20)
    return jsonify(news)

@app.route('/api/analytics/<ticker>', methods=['GET'])
def get_analytics(ticker):
    """Get advanced analytics for a stock"""
    analytics = get_advanced_analytics(ticker)
    if analytics:
        return jsonify(analytics)
    return jsonify({'error': 'Unable to fetch analytics'}), 404

@app.route('/api/backtest/<ticker>', methods=['GET'])
def backtest(ticker):
    """Run backtest for a stock"""
    result = backtest_strategy(ticker)
    if result:
        return jsonify(result)
    return jsonify({'error': 'Unable to run backtest'}), 404

@app.route('/api/historical/<ticker>', methods=['GET'])
def get_historical(ticker):
    """Get historical data for a stock (for charting)"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1y')
        
        if hist.empty:
            return jsonify({'error': 'No data available'}), 404
        
        data = {
            'dates': hist.index.strftime('%Y-%m-%d').tolist(),
            'open': hist['Open'].tolist(),
            'high': hist['High'].tolist(),
            'low': hist['Low'].tolist(),
            'close': hist['Close'].tolist(),
            'volume': hist['Volume'].tolist(),
        }
        
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/<ticker>', methods=['GET'])
def export_data(ticker):
    """Export stock data to CSV"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1y')
        info = stock.info
        
        # Create CSV in memory
        output = io.StringIO()
        hist.to_csv(output)
        output.seek(0)
        
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{ticker}_data.csv'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
