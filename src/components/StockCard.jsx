import React, { useState } from 'react';
import MiniSparkline from './MiniSparkline';
import StockDetailModal from './StockDetailModal';

const StockCard = ({ stock }) => {
  const [showModal, setShowModal] = useState(false);
  
  const isFlashSignal = stock.alpeshRating >= 9 && stock.returnAlpha > 0 && stock.pegRatio < 1.0;
  
  const priceChangeColor = stock.priceChange6m >= 0 ? 'text-green-400' : 'text-red-400';
  const priceChangeSign = stock.priceChange6m >= 0 ? '+' : '';
  
  // Check if price is above or below 200-day MA
  const aboveMA200 = stock.ma200 ? stock.price > stock.ma200 : null;
  const ma200Color = aboveMA200 === null ? 'text-gray-400' : aboveMA200 ? 'text-green-400' : 'text-red-400';
  const ma200Icon = aboveMA200 === null ? '' : aboveMA200 ? '↑' : '↓';

  return (
    <>
      <div 
        onClick={() => setShowModal(true)}
        className={`glass-panel glass-shadow glass-hover rounded-2xl p-5 cursor-pointer group
          ${isFlashSignal ? 'alpesh-signal' : ''}`}
      >
        <div className="flex justify-between items-start mb-3">
          <div>
            <h3 className="text-xl font-bold text-white">{stock.ticker}</h3>
            <p className="text-xs text-gray-400 truncate max-w-[150px]">{stock.name}</p>
            <span className="text-xs text-purple-300 mt-1 inline-block">{stock.sector}</span>
          </div>
          <div className="glass-panel px-2 py-1 rounded-lg">
            <span className="text-xs text-yellow-400">★ {stock.alpeshRating}</span>
          </div>
        </div>

        <div className="mb-3">
          <div className="text-2xl font-bold text-white">${stock.price.toFixed(2)}</div>
          <div className="flex items-center justify-between">
            <div className={`text-sm ${priceChangeColor}`}>
              {priceChangeSign}{stock.priceChange6m.toFixed(2)}% (6M)
            </div>
            {stock.ma200 && (
              <div className={`text-xs ${ma200Color}`}>
                {ma200Icon} MA200: ${stock.ma200.toFixed(2)}
              </div>
            )}
          </div>
        </div>

        <MiniSparkline data={stock.priceHistory} />

        <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
          <div className="glass-panel rounded-lg p-2">
            <div className="text-gray-400">CROCI</div>
            <div className="text-white font-semibold">{stock.croci.toFixed(1)}%</div>
          </div>
          <div className="glass-panel rounded-lg p-2">
            <div className="text-gray-400">PEG</div>
            <div className="text-white font-semibold">{stock.pegRatio.toFixed(2)}</div>
          </div>
          <div className="glass-panel rounded-lg p-2">
            <div className="text-gray-400">Alpha</div>
            <div className={`font-semibold ${stock.returnAlpha >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {stock.returnAlpha.toFixed(1)}%
            </div>
          </div>
          <div className="glass-panel rounded-lg p-2">
            <div className="text-gray-400">Inst. Own</div>
            <div className="text-white font-semibold">{stock.institutionalOwnership?.toFixed(0) || '0'}%</div>
          </div>
        </div>

        {isFlashSignal && (
          <div className="mt-3 glass-panel rounded-lg p-2 bg-green-500/20 border border-green-400/50">
            <p className="text-xs text-green-300 text-center font-semibold">🎯 SIGNAL DETECTED</p>
          </div>
        )}
        
        <div className="mt-3 text-center text-xs text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">
          Click for detailed analysis →
        </div>
      </div>

      {showModal && <StockDetailModal stock={stock} onClose={() => setShowModal(false)} />}
    </>
  );
};

export default StockCard;
