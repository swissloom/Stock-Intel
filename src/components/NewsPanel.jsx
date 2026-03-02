import React, { useState, useEffect } from 'react';

const NewsPanel = ({ ticker }) => {
  const [news, setNews] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (ticker) {
      fetchNews();
    }
  }, [ticker]);

  const fetchNews = async () => {
    setLoading(true);
    try {
      const endpoint = ticker 
        ? `http://localhost:5000/api/news/${ticker}`
        : 'http://localhost:5000/api/market-news';
      
      const response = await fetch(endpoint);
      const data = await response.json();
      setNews(data);
    } catch (error) {
      console.error('Error fetching news:', error);
    }
    setLoading(false);
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    
    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
  };

  if (loading) {
    return (
      <div className="glass-panel glass-shadow rounded-2xl p-4">
        <p className="text-gray-400 text-sm">Loading news...</p>
      </div>
    );
  }

  return (
    <div className="glass-panel glass-shadow rounded-2xl p-4 max-h-96 overflow-y-auto">
      <h3 className="text-lg font-semibold text-white mb-4">
        {ticker ? `${ticker} News` : 'Market News'}
      </h3>
      
      <div className="space-y-3">
        {news.map((item, index) => (
          <a
            key={index}
            href={item.link}
            target="_blank"
            rel="noopener noreferrer"
            className="block glass-panel rounded-lg p-3 hover:bg-white/10 transition-all"
          >
            <div className="flex gap-3">
              {item.thumbnail && (
                <img 
                  src={item.thumbnail} 
                  alt="" 
                  className="w-16 h-16 rounded object-cover flex-shrink-0"
                />
              )}
              <div className="flex-1 min-w-0">
                <h4 className="text-white text-sm font-medium line-clamp-2 mb-1">
                  {item.title}
                </h4>
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  <span>{item.publisher}</span>
                  <span>•</span>
                  <span>{formatDate(item.publishedAt)}</span>
                </div>
              </div>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
};

export default NewsPanel;
