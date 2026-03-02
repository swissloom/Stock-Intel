import React, { useState } from 'react';
import NewsPanel from './NewsPanel';
import AnalyticsPanel from './AnalyticsPanel';

const StockDetailModal = ({ stock, onClose }) => {
  const [activeTab, setActiveTab] = useState('overview');
  
  if (!stock) return null;

  const analystScore = stock.analystRating 
    ? (stock.analystRating.strongBuy * 2 + stock.analystRating.buy - stock.analystRating.sell - stock.analystRating.strongSell * 2)
    : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm"></div>
      
      <div 
        className="relative glass-panel glass-shadow rounded-3xl p-6 max-w-6xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-white text-2xl z-10"
        >
          ×
        </button>

        <div className="mb-6">
          <h2 className="text-3xl font-bold text-white mb-2">{stock.ticker}</h2>
          <p className="text-gray-300">{stock.name}</p>
          <span className="text-sm text-purple-300">{stock.sector}</span>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 border-b border-white/10">
          <button
            onClick={() => setActiveTab('overview')}
            className={`px-4 py-2 text-sm font-medium transition-all ${
              activeTab === 'overview'
                ? 'text-white border-b-2 border-purple-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Overview
          </button>
          <button
            onClick={() => setActiveTab('analytics')}
            className={`px-4 py-2 text-sm font-medium transition-all ${
              activeTab === 'analytics'
                ? 'text-white border-b-2 border-purple-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            Analytics & Backtest
          </button>
          <button
            onClick={() => setActiveTab('news')}
            className={`px-4 py-2 text-sm font-medium transition-all ${
              activeTab === 'news'
                ? 'text-white border-b-2 border-purple-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            News & Research
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === 'overview' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Price & Valuation */}
            <div className="glass-panel rounded-xl p-4">
              <h3 className="text-lg font-semibold text-white mb-3">Price & Valuation</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Current Price</span>
                  <span className="text-white font-semibold">${stock.price.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Market Cap</span>
                  <span className="text-white">${stock.marketCap.toFixed(2)}B</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">P/E Ratio (Forward)</span>
                  <span className="text-white">{stock.forwardPE?.toFixed(2) || 'N/A'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">PEG Ratio</span>
                  <span className="text-white">{stock.pegRatio.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Price to Book</span>
                  <span className="text-white">{stock.priceToBook?.toFixed(2) || 'N/A'}</span>
                </div>
              </div>
            </div>

            {/* Technical Indicators */}
            <div className="glass-panel rounded-xl p-4">
              <h3 className="text-lg font-semibold text-white mb-3">Technical Indicators</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">50-Day MA</span>
                  <span className="text-white">${stock.ma50?.toFixed(2) || 'N/A'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">200-Day MA</span>
                  <span className="text-white">${stock.ma200?.toFixed(2) || 'N/A'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">RSI (14)</span>
                  <span className={`font-semibold ${
                    stock.rsi > 70 ? 'text-red-400' : stock.rsi < 30 ? 'text-green-400' : 'text-white'
                  }`}>
                    {stock.rsi?.toFixed(1) || 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Beta</span>
                  <span className="text-white">{stock.beta?.toFixed(2) || 'N/A'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">6M Change</span>
                  <span className={stock.priceChange6m >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {stock.priceChange6m >= 0 ? '+' : ''}{stock.priceChange6m.toFixed(2)}%
                  </span>
                </div>
              </div>
            </div>

            {/* Institutional Data */}
            <div className="glass-panel rounded-xl p-4">
              <h3 className="text-lg font-semibold text-white mb-3">Institutional Metrics</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Institutional Ownership</span>
                  <span className="text-white font-semibold">{stock.institutionalOwnership?.toFixed(1) || '0'}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Short Ratio</span>
                  <span className="text-white">{stock.shortRatio?.toFixed(2) || 'N/A'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Volume</span>
                  <span className="text-white">{(stock.volume / 1e6)?.toFixed(2) || '0'}M</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Avg Volume</span>
                  <span className="text-white">{(stock.avgVolume / 1e6)?.toFixed(2) || '0'}M</span>
                </div>
              </div>
            </div>

            {/* Analyst Ratings */}
            {stock.analystRating && (
              <div className="glass-panel rounded-xl p-4">
                <h3 className="text-lg font-semibold text-white mb-3">Analyst Ratings</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-green-400">Strong Buy</span>
                    <span className="text-white">{stock.analystRating.strongBuy || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-green-300">Buy</span>
                    <span className="text-white">{stock.analystRating.buy || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-yellow-400">Hold</span>
                    <span className="text-white">{stock.analystRating.hold || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-red-300">Sell</span>
                    <span className="text-white">{stock.analystRating.sell || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-red-400">Strong Sell</span>
                    <span className="text-white">{stock.analystRating.strongSell || 0}</span>
                  </div>
                  <div className="mt-3 pt-3 border-t border-white/10">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Consensus Score</span>
                      <span className={`font-semibold ${
                        analystScore > 5 ? 'text-green-400' : analystScore < -5 ? 'text-red-400' : 'text-yellow-400'
                      }`}>
                        {analystScore > 0 ? '+' : ''}{analystScore}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Financial Health */}
            <div className="glass-panel rounded-xl p-4">
              <h3 className="text-lg font-semibold text-white mb-3">Financial Health</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">ROE</span>
                  <span className="text-white">{stock.returnOnEquity?.toFixed(1) || '0'}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Profit Margin</span>
                  <span className="text-white">{stock.profitMargin?.toFixed(1) || '0'}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Operating Margin</span>
                  <span className="text-white">{stock.operatingMargin?.toFixed(1) || '0'}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Debt to Equity</span>
                  <span className="text-white">{stock.debtToEquity?.toFixed(2) || 'N/A'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Free Cash Flow</span>
                  <span className="text-white">${stock.freeCashFlow?.toFixed(2) || '0'}B</span>
                </div>
              </div>
            </div>

            {/* Growth Metrics */}
            <div className="glass-panel rounded-xl p-4">
              <h3 className="text-lg font-semibold text-white mb-3">Growth Metrics</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Revenue Growth</span>
                  <span className={stock.revenueGrowth >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {stock.revenueGrowth >= 0 ? '+' : ''}{stock.revenueGrowth?.toFixed(1) || '0'}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Earnings Growth</span>
                  <span className={stock.earningsGrowth >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {stock.earningsGrowth >= 0 ? '+' : ''}{stock.earningsGrowth?.toFixed(1) || '0'}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Dividend Yield</span>
                  <span className="text-white">{stock.dividendYield?.toFixed(2) || '0'}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Alpesh Rating</span>
                  <span className="text-yellow-400 font-semibold">★ {stock.alpeshRating}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'analytics' && (
          <AnalyticsPanel ticker={stock.ticker} />
        )}

        {activeTab === 'news' && (
          <NewsPanel ticker={stock.ticker} />
        )}
      </div>
    </div>
  );
};

export default StockDetailModal;
