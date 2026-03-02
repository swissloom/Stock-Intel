import React, { useState } from 'react';
import StockDetailModal from './StockDetailModal';

const StockListView = ({ stocks, loading }) => {
  const [sortField, setSortField] = useState('ticker');
  const [sortDirection, setSortDirection] = useState('asc');
  const [selectedStock, setSelectedStock] = useState(null);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const sortedStocks = [...stocks].sort((a, b) => {
    let aVal = a[sortField];
    let bVal = b[sortField];

    // Handle null/undefined values
    if (aVal === null || aVal === undefined) aVal = 0;
    if (bVal === null || bVal === undefined) bVal = 0;

    if (typeof aVal === 'string') {
      return sortDirection === 'asc' 
        ? aVal.localeCompare(bVal)
        : bVal.localeCompare(aVal);
    }

    return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
  });

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <span className="text-gray-600">⇅</span>;
    return sortDirection === 'asc' ? <span className="text-purple-400">↑</span> : <span className="text-purple-400">↓</span>;
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="glass-panel glass-shadow rounded-2xl px-8 py-6">
          <p className="text-white text-lg">Loading market data...</p>
        </div>
      </div>
    );
  }

  if (stocks.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="glass-panel glass-shadow rounded-2xl px-8 py-6">
          <p className="text-white text-lg">No stocks match your criteria</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-hidden flex flex-col px-4 pb-4">
      <div className="glass-panel glass-shadow rounded-2xl overflow-hidden flex-1 flex flex-col">
        <div className="overflow-x-auto overflow-y-auto flex-1">
          <table className="w-full">
            <thead className="sticky top-0 glass-panel">
              <tr className="text-left text-sm text-yellow-500 font-semibold">
                <th 
                  className="px-4 py-3 cursor-pointer hover:bg-white/5 transition-colors"
                  onClick={() => handleSort('ticker')}
                >
                  <div className="flex items-center gap-2">
                    Ticker <SortIcon field="ticker" />
                  </div>
                </th>
                <th 
                  className="px-4 py-3 cursor-pointer hover:bg-white/5 transition-colors"
                  onClick={() => handleSort('name')}
                >
                  <div className="flex items-center gap-2">
                    Name <SortIcon field="name" />
                  </div>
                </th>
                <th 
                  className="px-4 py-3 cursor-pointer hover:bg-white/5 transition-colors"
                  onClick={() => handleSort('sector')}
                >
                  <div className="flex items-center gap-2">
                    Sector <SortIcon field="sector" />
                  </div>
                </th>
                <th 
                  className="px-4 py-3 cursor-pointer hover:bg-white/5 transition-colors text-right"
                  onClick={() => handleSort('price')}
                >
                  <div className="flex items-center justify-end gap-2">
                    Price <SortIcon field="price" />
                  </div>
                </th>
                <th 
                  className="px-4 py-3 cursor-pointer hover:bg-white/5 transition-colors text-right"
                  onClick={() => handleSort('priceChange6m')}
                >
                  <div className="flex items-center justify-end gap-2">
                    6M Change <SortIcon field="priceChange6m" />
                  </div>
                </th>
                <th 
                  className="px-4 py-3 cursor-pointer hover:bg-white/5 transition-colors text-right"
                  onClick={() => handleSort('marketCap')}
                >
                  <div className="flex items-center justify-end gap-2">
                    Market Cap <SortIcon field="marketCap" />
                  </div>
                </th>
                <th 
                  className="px-4 py-3 cursor-pointer hover:bg-white/5 transition-colors text-right"
                  onClick={() => handleSort('pegRatio')}
                >
                  <div className="flex items-center justify-end gap-2">
                    PEG <SortIcon field="pegRatio" />
                  </div>
                </th>
                <th 
                  className="px-4 py-3 cursor-pointer hover:bg-white/5 transition-colors text-right"
                  onClick={() => handleSort('alpeshRating')}
                >
                  <div className="flex items-center justify-end gap-2">
                    Rating <SortIcon field="alpeshRating" />
                  </div>
                </th>
                <th 
                  className="px-4 py-3 cursor-pointer hover:bg-white/5 transition-colors text-right"
                  onClick={() => handleSort('returnAlpha')}
                >
                  <div className="flex items-center justify-end gap-2">
                    Alpha <SortIcon field="returnAlpha" />
                  </div>
                </th>
                <th 
                  className="px-4 py-3 cursor-pointer hover:bg-white/5 transition-colors text-right"
                  onClick={() => handleSort('institutionalOwnership')}
                >
                  <div className="flex items-center justify-end gap-2">
                    Inst. Own <SortIcon field="institutionalOwnership" />
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedStocks.map((stock) => {
                const isSignal = stock.alpeshRating >= 9 && stock.returnAlpha > 0 && stock.pegRatio < 1.0;
                
                return (
                  <tr
                    key={stock.ticker}
                    onClick={() => setSelectedStock(stock)}
                    className={`border-t border-white/10 hover:bg-white/10 cursor-pointer text-sm glass-hover ${
                      isSignal ? 'bg-green-500/10 alpesh-signal-row' : ''
                    }`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white">{stock.ticker}</span>
                        {isSignal && <span className="text-green-400 text-xs">🎯</span>}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-300 max-w-xs truncate">
                      {stock.name}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-purple-300 text-xs">{stock.sector}</span>
                    </td>
                    <td className="px-4 py-3 text-right text-white font-semibold">
                      ${stock.price.toFixed(2)}
                    </td>
                    <td className={`px-4 py-3 text-right font-semibold ${
                      stock.priceChange6m >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {stock.priceChange6m >= 0 ? '+' : ''}{stock.priceChange6m.toFixed(2)}%
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300">
                      ${stock.marketCap.toFixed(2)}B
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300">
                      {stock.pegRatio.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-yellow-400">★ {stock.alpeshRating}</span>
                    </td>
                    <td className={`px-4 py-3 text-right font-semibold ${
                      stock.returnAlpha >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {stock.returnAlpha >= 0 ? '+' : ''}{stock.returnAlpha.toFixed(1)}%
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300">
                      {stock.institutionalOwnership?.toFixed(0) || '0'}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {selectedStock && (
        <StockDetailModal 
          stock={selectedStock} 
          onClose={() => setSelectedStock(null)} 
        />
      )}
    </div>
  );
};

export default StockListView;
