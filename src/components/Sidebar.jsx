import React from 'react';

const Sidebar = ({ activeFilter, setActiveFilter, activeSector, setActiveSector, activeView, setActiveView }) => {
  const views = [
    { id: 'stocks', label: 'Stock Screener', icon: '📊' },
    { id: 'depth', label: 'Market Depth', icon: '📉' },
    { id: 'news', label: 'Market News', icon: '📰' },
  ];

  const filters = [
    { id: 'all', label: 'All Stocks', icon: '📊' },
    { id: 'signals', label: 'Signal Detected', icon: '🎯' },
    { id: 'topRated', label: 'Top Rated', icon: '⭐' },
    { id: 'highGrowth', label: 'High Growth', icon: '📈' },
    { id: 'highCROCI', label: 'High CROCI', icon: '💎' },
  ];

  const sectors = [
    { id: 'all', label: 'All Sectors', icon: '🌐' },
    { id: 'Technology', label: 'Technology', icon: '💻' },
    { id: 'Finance', label: 'Finance', icon: '💰' },
    { id: 'Consumer', label: 'Consumer', icon: '🛒' },
    { id: 'Healthcare', label: 'Healthcare', icon: '🏥' },
    { id: 'Industrial', label: 'Industrial', icon: '🏭' },
    { id: 'Energy', label: 'Energy', icon: '⚡' },
    { id: 'Telecom', label: 'Telecom', icon: '📡' },
    { id: 'ETFs', label: 'ETFs', icon: '📦' },
  ];

  return (
    <div className="w-64 p-4 glass-panel glass-shadow m-4 rounded-3xl overflow-y-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white mb-1">Stock Intel</h1>
        <p className="text-sm text-gray-300">Market Dashboard</p>
      </div>

      <div className="mb-6">
        <h2 className="text-xs uppercase text-gray-400 mb-2 px-2">Views</h2>
        <nav className="space-y-1">
          {views.map((view) => (
            <button
              key={view.id}
              onClick={() => setActiveView(view.id)}
              className={`w-full text-left px-4 py-2.5 rounded-xl transition-all duration-300 group
                ${activeView === view.id 
                  ? 'glass-panel text-white' 
                  : 'text-gray-300 hover:text-white hover:bg-white/5'
                }`}
            >
              <div className="flex items-center space-x-3">
                <span className="text-lg">{view.icon}</span>
                <span className="font-medium text-sm">{view.label}</span>
              </div>
            </button>
          ))}
        </nav>
      </div>

      <div className="mb-6">
        <h2 className="text-xs uppercase text-gray-400 mb-2 px-2">Filters</h2>
        <nav className="space-y-1">
          {filters.map((filter) => (
            <button
              key={filter.id}
              onClick={() => setActiveFilter(filter.id)}
              className={`w-full text-left px-4 py-2.5 rounded-xl transition-all duration-300 group
                ${activeFilter === filter.id 
                  ? 'glass-panel text-white' 
                  : 'text-gray-300 hover:text-white hover:bg-white/5'
                }`}
            >
              <div className="flex items-center space-x-3">
                <span className="text-lg">{filter.icon}</span>
                <span className="font-medium text-sm">{filter.label}</span>
              </div>
            </button>
          ))}
        </nav>
      </div>

      <div>
        <h2 className="text-xs uppercase text-gray-400 mb-2 px-2">Sectors</h2>
        <nav className="space-y-1">
          {sectors.map((sector) => (
            <button
              key={sector.id}
              onClick={() => setActiveSector(sector.id)}
              className={`w-full text-left px-4 py-2.5 rounded-xl transition-all duration-300 group
                ${activeSector === sector.id 
                  ? 'glass-panel text-white' 
                  : 'text-gray-300 hover:text-white hover:bg-white/5'
                }`}
            >
              <div className="flex items-center space-x-3">
                <span className="text-lg">{sector.icon}</span>
                <span className="font-medium text-sm">{sector.label}</span>
              </div>
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
};

export default Sidebar;
