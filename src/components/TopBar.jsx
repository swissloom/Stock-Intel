import React, { useState, useEffect } from 'react';

const TopBar = ({ searchQuery, setSearchQuery, viewMode, setViewMode, activeView }) => {
  const [marketStatus, setMarketStatus] = useState({ isOpen: false, status: 'Closed' });

  useEffect(() => {
    const checkMarketStatus = () => {
      const now = new Date();
      const nyTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
      const day = nyTime.getDay(); // 0 = Sunday, 6 = Saturday
      const hours = nyTime.getHours();
      const minutes = nyTime.getMinutes();
      const timeInMinutes = hours * 60 + minutes;
      
      // Market hours: Monday-Friday, 9:30 AM - 4:00 PM ET
      const marketOpen = 9 * 60 + 30; // 9:30 AM
      const marketClose = 16 * 60; // 4:00 PM
      
      const isWeekday = day >= 1 && day <= 5;
      const isDuringMarketHours = timeInMinutes >= marketOpen && timeInMinutes < marketClose;
      
      if (isWeekday && isDuringMarketHours) {
        setMarketStatus({ isOpen: true, status: 'Open' });
      } else if (isWeekday && timeInMinutes >= marketClose) {
        setMarketStatus({ isOpen: false, status: 'Closed' });
      } else if (isWeekday && timeInMinutes < marketOpen) {
        setMarketStatus({ isOpen: false, status: 'Pre-Market' });
      } else {
        setMarketStatus({ isOpen: false, status: 'Closed' });
      }
    };

    checkMarketStatus();
    const interval = setInterval(checkMarketStatus, 60000); // Check every minute

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-4">
      <div className="glass-panel glass-shadow rounded-2xl px-6 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex-1 relative">
            <input
              type="text"
              placeholder="Search stocks by ticker or name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-white/10 backdrop-blur-xl border border-white/20 rounded-xl px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-400/50 transition-all"
            />
            <span className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
          </div>
          
          {activeView === 'stocks' && (
            <div className="flex gap-2">
              <button
                onClick={() => setViewMode('grid')}
                className={`px-4 py-2 rounded-lg transition-all ${
                  viewMode === 'grid'
                    ? 'glass-panel text-white'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
                title="Grid View"
              >
                ⊞
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`px-4 py-2 rounded-lg transition-all ${
                  viewMode === 'list'
                    ? 'glass-panel text-white'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
                title="List View"
              >
                ☰
              </button>
            </div>
          )}
          
          <div className="text-white text-sm">
            <span className="text-gray-400">US Market:</span>
            <span className={`ml-2 ${marketStatus.isOpen ? 'text-green-400' : 'text-red-400'}`}>
              ● {marketStatus.status}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TopBar;
