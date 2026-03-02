import React, { useState, useEffect } from 'react';
import MeshGradientBackground from './components/MeshGradientBackground';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import StockGrid from './components/StockGrid';
import StockListView from './components/StockListView';
import MarketDepthPanel from './components/MarketDepthPanel';
import NewsPanel from './components/NewsPanel';
import { fetchStockData } from './services/stockService';

function App() {
  const [stocks, setStocks] = useState([]);
  const [filteredStocks, setFilteredStocks] = useState([]);
  const [activeFilter, setActiveFilter] = useState('all');
  const [activeSector, setActiveSector] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState('stocks'); // 'stocks', 'list', 'depth', 'news'
  const [viewMode, setViewMode] = useState('grid'); // 'grid' or 'list'

  useEffect(() => {
    loadStockData();
  }, []);

  useEffect(() => {
    applyFilters();
  }, [stocks, activeFilter, activeSector, searchQuery]);

  const loadStockData = async () => {
    setLoading(true);
    const data = await fetchStockData();
    setStocks(data);
    setLoading(false);
  };

  const applyFilters = () => {
    let filtered = [...stocks];

    // Apply category filter
    if (activeFilter === 'signals') {
      filtered = filtered.filter(s => 
        s.alpeshRating >= 9 && s.returnAlpha > 0 && s.pegRatio < 1.0
      );
    } else if (activeFilter === 'topRated') {
      filtered = filtered.filter(s => s.alpeshRating >= 8);
    } else if (activeFilter === 'highGrowth') {
      filtered = filtered.filter(s => s.priceChange6m > 15);
    } else if (activeFilter === 'highCROCI') {
      filtered = filtered.filter(s => s.croci > 10);
    }

    // Apply sector filter
    if (activeSector !== 'all') {
      filtered = filtered.filter(s => s.sector === activeSector);
    }

    // Apply search filter
    if (searchQuery) {
      filtered = filtered.filter(s => 
        s.ticker.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.name.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    setFilteredStocks(filtered);
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden">
      <MeshGradientBackground />
      
      <div className="relative z-10 flex h-full">
        <Sidebar 
          activeFilter={activeFilter} 
          setActiveFilter={setActiveFilter}
          activeSector={activeSector}
          setActiveSector={setActiveSector}
          activeView={activeView}
          setActiveView={setActiveView}
        />
        
        <div className="flex-1 flex flex-col overflow-hidden">
          <TopBar 
            searchQuery={searchQuery} 
            setSearchQuery={setSearchQuery}
            viewMode={viewMode}
            setViewMode={setViewMode}
            activeView={activeView}
          />
          
          {activeView === 'stocks' && (
            <>
              {viewMode === 'grid' ? (
                <StockGrid stocks={filteredStocks} loading={loading} />
              ) : (
                <StockListView stocks={filteredStocks} loading={loading} />
              )}
            </>
          )}
          
          {activeView === 'depth' && (
            <div className="flex-1 overflow-y-auto px-4 pb-4">
              <MarketDepthPanel stocks={stocks} />
            </div>
          )}
          
          {activeView === 'news' && (
            <div className="flex-1 overflow-y-auto px-4 pb-4">
              <NewsPanel ticker={null} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
