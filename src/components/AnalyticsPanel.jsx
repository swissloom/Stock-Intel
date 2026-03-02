import React, { useState, useEffect } from 'react';

const AnalyticsPanel = ({ ticker }) => {
  const [analytics, setAnalytics] = useState(null);
  const [backtest, setBacktest] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (ticker) {
      fetchAnalytics();
      fetchBacktest();
    }
  }, [ticker]);

  const fetchAnalytics = async () => {
    try {
      const response = await fetch(`http://localhost:5000/api/analytics/${ticker}`);
      const data = await response.json();
      setAnalytics(data);
    } catch (error) {
      console.error('Error fetching analytics:', error);
    }
  };

  const fetchBacktest = async () => {
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:5000/api/backtest/${ticker}`);
      const data = await response.json();
      setBacktest(data);
    } catch (error) {
      console.error('Error fetching backtest:', error);
    }
    setLoading(false);
  };

  const exportToCSV = () => {
    window.open(`http://localhost:5000/api/export/${ticker}`, '_blank');
  };

  if (loading || !analytics) {
    return (
      <div className="glass-panel glass-shadow rounded-2xl p-4">
        <p className="text-gray-400 text-sm">Loading analytics...</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Advanced Analytics */}
      <div className="glass-panel glass-shadow rounded-2xl p-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-white">Advanced Analytics</h3>
          <button
            onClick={exportToCSV}
            className="glass-panel px-3 py-1 rounded-lg text-xs text-white hover:bg-white/10 transition-all"
          >
            📊 Export to CSV
          </button>
        </div>
        
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="glass-panel rounded-lg p-3">
            <div className="text-gray-400 mb-1">Sharpe Ratio</div>
            <div className={`text-lg font-semibold ${
              analytics.sharpeRatio > 1 ? 'text-green-400' : 
              analytics.sharpeRatio > 0 ? 'text-yellow-400' : 'text-red-400'
            }`}>
              {analytics.sharpeRatio?.toFixed(2) || 'N/A'}
            </div>
          </div>

          <div className="glass-panel rounded-lg p-3">
            <div className="text-gray-400 mb-1">Max Drawdown</div>
            <div className="text-lg font-semibold text-red-400">
              {analytics.maxDrawdown?.toFixed(2) || '0'}%
            </div>
          </div>

          <div className="glass-panel rounded-lg p-3">
            <div className="text-gray-400 mb-1">Volatility (Annual)</div>
            <div className="text-lg font-semibold text-white">
              {analytics.volatility?.toFixed(2) || '0'}%
            </div>
          </div>

          <div className="glass-panel rounded-lg p-3">
            <div className="text-gray-400 mb-1">52W High/Low</div>
            <div className="text-xs text-white">
              ${analytics.highLow52Week?.high?.toFixed(2)} / ${analytics.highLow52Week?.low?.toFixed(2)}
            </div>
          </div>
        </div>

        {/* Price Changes */}
        <div className="mt-4">
          <div className="text-gray-400 text-xs mb-2">Price Performance</div>
          <div className="grid grid-cols-4 gap-2 text-xs">
            <div className="glass-panel rounded p-2 text-center">
              <div className="text-gray-400">1M</div>
              <div className={analytics.priceChange?.['1m'] >= 0 ? 'text-green-400' : 'text-red-400'}>
                {analytics.priceChange?.['1m'] >= 0 ? '+' : ''}{analytics.priceChange?.['1m']?.toFixed(1)}%
              </div>
            </div>
            <div className="glass-panel rounded p-2 text-center">
              <div className="text-gray-400">3M</div>
              <div className={analytics.priceChange?.['3m'] >= 0 ? 'text-green-400' : 'text-red-400'}>
                {analytics.priceChange?.['3m'] >= 0 ? '+' : ''}{analytics.priceChange?.['3m']?.toFixed(1)}%
              </div>
            </div>
            <div className="glass-panel rounded p-2 text-center">
              <div className="text-gray-400">6M</div>
              <div className={analytics.priceChange?.['6m'] >= 0 ? 'text-green-400' : 'text-red-400'}>
                {analytics.priceChange?.['6m'] >= 0 ? '+' : ''}{analytics.priceChange?.['6m']?.toFixed(1)}%
              </div>
            </div>
            <div className="glass-panel rounded p-2 text-center">
              <div className="text-gray-400">1Y</div>
              <div className={analytics.priceChange?.['1y'] >= 0 ? 'text-green-400' : 'text-red-400'}>
                {analytics.priceChange?.['1y'] >= 0 ? '+' : ''}{analytics.priceChange?.['1y']?.toFixed(1)}%
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Backtest Results */}
      {backtest && (
        <div className="glass-panel glass-shadow rounded-2xl p-4">
          <h3 className="text-lg font-semibold text-white mb-4">Backtest: Buy & Hold (1Y)</h3>
          
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Initial Capital</span>
              <span className="text-white font-semibold">${backtest.initialCapital.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Final Value</span>
              <span className="text-white font-semibold">${backtest.finalValue.toFixed(2).toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Total Return</span>
              <span className={`font-semibold text-lg ${
                backtest.totalReturn >= 0 ? 'text-green-400' : 'text-red-400'
              }`}>
                {backtest.totalReturn >= 0 ? '+' : ''}{backtest.totalReturn.toFixed(2)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Shares Purchased</span>
              <span className="text-white">{backtest.shares.toFixed(4)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AnalyticsPanel;
