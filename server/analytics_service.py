import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def calculate_sharpe_ratio(returns, risk_free_rate=0.02):
    """Calculate Sharpe Ratio"""
    if len(returns) == 0:
        return 0
    excess_returns = returns - (risk_free_rate / 252)
    return np.sqrt(252) * excess_returns.mean() / excess_returns.std() if excess_returns.std() != 0 else 0

def calculate_max_drawdown(prices):
    """Calculate maximum drawdown"""
    if len(prices) == 0:
        return 0
    cumulative = (1 + prices.pct_change()).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    return drawdown.min()

def calculate_volatility(returns):
    """Calculate annualized volatility"""
    if len(returns) == 0:
        return 0
    return returns.std() * np.sqrt(252)

def get_advanced_analytics(ticker):
    """Get advanced analytics for a stock"""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        
        # Get 1 year of historical data
        hist = stock.history(period='1y')
        
        if hist.empty:
            return None
        
        returns = hist['Close'].pct_change().dropna()
        
        analytics = {
            'sharpeRatio': calculate_sharpe_ratio(returns),
            'maxDrawdown': calculate_max_drawdown(hist['Close']) * 100,
            'volatility': calculate_volatility(returns) * 100,
            'avgVolume': hist['Volume'].mean(),
            'highLow52Week': {
                'high': hist['High'].max(),
                'low': hist['Low'].min(),
            },
            'priceChange': {
                '1m': ((hist['Close'].iloc[-1] / hist['Close'].iloc[-21]) - 1) * 100 if len(hist) >= 21 else 0,
                '3m': ((hist['Close'].iloc[-1] / hist['Close'].iloc[-63]) - 1) * 100 if len(hist) >= 63 else 0,
                '6m': ((hist['Close'].iloc[-1] / hist['Close'].iloc[-126]) - 1) * 100 if len(hist) >= 126 else 0,
                '1y': ((hist['Close'].iloc[-1] / hist['Close'].iloc[0]) - 1) * 100,
            },
            'volumeProfile': {
                'avgDaily': hist['Volume'].mean(),
                'maxDaily': hist['Volume'].max(),
                'minDaily': hist['Volume'].min(),
            }
        }
        
        return analytics
    except Exception as e:
        print(f"Error calculating analytics for {ticker}: {str(e)}")
        return None

def backtest_strategy(ticker, initial_capital=10000, strategy='buy_hold'):
    """Simple backtesting for buy and hold strategy"""
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1y')
        
        if hist.empty:
            return None
        
        # Buy and hold strategy
        shares = initial_capital / hist['Close'].iloc[0]
        final_value = shares * hist['Close'].iloc[-1]
        total_return = ((final_value - initial_capital) / initial_capital) * 100
        
        return {
            'initialCapital': initial_capital,
            'finalValue': final_value,
            'totalReturn': total_return,
            'shares': shares,
            'strategy': strategy,
            'period': '1 year'
        }
    except Exception as e:
        print(f"Error backtesting {ticker}: {str(e)}")
        return None
