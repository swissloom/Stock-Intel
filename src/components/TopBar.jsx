import React from 'react';

const TopBar = ({ searchQuery, setSearchQuery, viewMode, setViewMode, activeView }) => {
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
            <span className="text-gray-400">Market Status:</span>
            <span className="ml-2 text-green-400">● Open</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TopBar;
