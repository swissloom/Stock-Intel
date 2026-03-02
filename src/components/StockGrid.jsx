import React from 'react';
import StockCard from './StockCard';

const StockGrid = ({ stocks, loading }) => {
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
    <div className="flex-1 overflow-y-auto px-4 pb-4">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {stocks.map((stock) => (
          <StockCard key={stock.ticker} stock={stock} />
        ))}
      </div>
    </div>
  );
};

export default StockGrid;
