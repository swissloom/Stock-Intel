import React from 'react';

const MarketDepthPanel = ({ stocks }) => {
  // Calculate market breadth metrics
  const advancing = stocks.filter(s => s.priceChange6m > 0).length;
  const declining = stocks.filter(s => s.priceChange6m < 0).length;
  const unchanged = stocks.length - advancing - declining;
  
  const advanceDeclineRatio = declining > 0 ? (advancing / declining).toFixed(2) : 'N/A';
  
  // Volume analysis
  const totalVolume = stocks.reduce((sum, s) => sum + (s.volume || 0), 0);
  const avgVolume = totalVolume / stocks.length;
  
  // Sector performance
  const sectorPerformance = {};
  stocks.forEach(stock => {
    if (!sectorPerformance[stock.sector]) {
      sectorPerformance[stock.sector] = { count: 0, totalChange: 0 };
    }
    sectorPerformance[stock.sector].count++;
    sectorPerformance[stock.sector].totalChange += stock.priceChange6m;
  });
  
  const sectorAvgs = Object.entries(sectorPerformance).map(([sector, data]) => ({
    sector,
    avgChange: data.totalChange / data.count,
    count: data.count
  })).sort((a, b) => b.avgChange - a.avgChange);

  return (
    <div className="glass-panel glass-shadow rounded-2xl p-6">
      <h2 className="text-2xl font-bold text-white mb-6">Market Depth & Breadth</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Market Breadth */}
        <div className="glass-panel rounded-xl p-4">
          <h3 className="text-lg font-semibold text-white mb-4">Market Breadth</h3>
          
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Advancing</span>
              <span className="text-green-400 font-semibold text-lg">{advancing}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Declining</span>
              <span className="text-red-400 font-semibold text-lg">{declining}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Unchanged</span>
              <span className="text-gray-300 font-semibold text-lg">{unchanged}</span>
            </div>
            
            <div className="pt-3 border-t border-white/10">
              <div className="flex justify-between items-center">
                <span className="text-gray-400">A/D Ratio</span>
                <span className={`font-semibold text-lg ${
                  parseFloat(advanceDeclineRatio) > 1 ? 'text-green-400' : 'text-red-400'
                }`}>
                  {advanceDeclineRatio}
                </span>
              </div>
            </div>
            
            {/* Visual bar */}
            <div className="mt-4">
              <div className="h-8 flex rounded-lg overflow-hidden">
                <div 
                  className="bg-green-500/50 flex items-center justify-center text-xs text-white"
                  style={{ width: `${(advancing / stocks.length) * 100}%` }}
                >
                  {((advancing / stocks.length) * 100).toFixed(0)}%
                </div>
                <div 
                  className="bg-red-500/50 flex items-center justify-center text-xs text-white"
                  style={{ width: `${(declining / stocks.length) * 100}%` }}
                >
                  {((declining / stocks.length) * 100).toFixed(0)}%
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Volume Analysis */}
        <div className="glass-panel rounded-xl p-4">
          <h3 className="text-lg font-semibold text-white mb-4">Volume Analysis</h3>
          
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-400">Total Volume</span>
              <span className="text-white font-semibold">
                {(totalVolume / 1e9).toFixed(2)}B
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Average Volume</span>
              <span className="text-white font-semibold">
                {(avgVolume / 1e6).toFixed(2)}M
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Stocks Tracked</span>
              <span className="text-white font-semibold">{stocks.length}</span>
            </div>
          </div>
        </div>

        {/* Sector Performance */}
        <div className="glass-panel rounded-xl p-4 md:col-span-2">
          <h3 className="text-lg font-semibold text-white mb-4">Sector Performance (6M)</h3>
          
          <div className="space-y-2">
            {sectorAvgs.map(({ sector, avgChange, count }) => (
              <div key={sector} className="flex items-center gap-3">
                <div className="w-32 text-sm text-gray-300">{sector}</div>
                <div className="flex-1">
                  <div className="h-6 bg-white/5 rounded-full overflow-hidden relative">
                    <div
                      className={`h-full ${avgChange >= 0 ? 'bg-green-500/50' : 'bg-red-500/50'}`}
                      style={{ 
                        width: `${Math.min(Math.abs(avgChange) * 2, 100)}%`,
                        marginLeft: avgChange < 0 ? 'auto' : '0'
                      }}
                    />
                  </div>
                </div>
                <div className={`w-20 text-right text-sm font-semibold ${
                  avgChange >= 0 ? 'text-green-400' : 'text-red-400'
                }`}>
                  {avgChange >= 0 ? '+' : ''}{avgChange.toFixed(1)}%
                </div>
                <div className="w-12 text-right text-xs text-gray-400">
                  ({count})
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default MarketDepthPanel;
