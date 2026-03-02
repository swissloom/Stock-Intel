// Yahoo Finance via Railway backend
const BACKEND_URL = 'https://stock-intel-production.up.railway.app';

const STOCK_DATA = {
  Technology: [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'NFLX', 'ADBE', 'CRM',
    'ORCL', 'INTC', 'AMD', 'QCOM', 'AVGO', 'CSCO', 'IBM', 'NOW', 'INTU', 'AMAT',
    'TSM', 'ASML', 'MU', 'LRCX', 'KLAC', 'MCHP', 'SHOP', 'SNOW', 'DDOG', 'NET', 'CRWD', 'ZS'
  ],
  Finance: [
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'SPGI',
    'V', 'MA', 'PYPL', 'SQ', 'COIN'
  ],
  Consumer: [
    'WMT', 'COST', 'HD', 'TGT', 'LOW', 'NKE', 'SBUX', 'MCD', 'DIS', 'BKNG',
    'PG', 'KO', 'PEP', 'PM', 'MDLZ', 'CL', 'EL', 'TSLA'
  ],
  Healthcare: [
    'UNH', 'JNJ', 'LLY', 'PFE', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'BMY'
  ],
  Industrial: [
    'BA', 'CAT', 'GE', 'HON', 'MMM', 'LMT', 'RTX', 'UPS', 'DE', 'F', 'GM', 'RIVN', 'LCID'
  ],
  Energy: [
    'XOM', 'CVX', 'COP', 'SLB', 'EOG'
  ],
  Telecom: [
    'T', 'VZ', 'TMUS', 'CMCSA', 'CHTR'
  ],
  ETFs: [
    'SPY', 'QQQ', 'IWM', 'DIA', 'VOO', 'VTI', 'EEM', 'GLD', 'SLV', 'TLT',
    'HYG', 'LQD', 'XLF', 'XLE', 'XLK', 'XLV', 'XLI', 'XLP', 'XLY', 'XLU',
    'ARKK', 'ARKG', 'VNQ', 'EFA', 'AGG', 'BND'
  ],
  Other: ['BRK.B']
};

const TICKERS = Object.values(STOCK_DATA).flat();

// Fetch stock data from local backend
const fetchYahooFinanceData = async () => {
  try {
    const response = await fetch(`${BACKEND_URL}/api/stocks`);

    if (!response.ok) {
      throw new Error(`API Error: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching Yahoo Finance data:', error);
    return null;
  }
};

// Generate price history for sparkline
const generatePriceHistory = (currentPrice, volatility = 0.02) => {
  const history = [];
  let price = currentPrice * 0.95; // Start slightly lower
  for (let i = 0; i < 30; i++) {
    price += (Math.random() - 0.48) * (currentPrice * volatility);
    history.push(Math.max(price, currentPrice * 0.7));
  }
  history[history.length - 1] = currentPrice; // End at current price
  return history;
};

// Calculate Alpesh rating based on multiple factors
const calculateAlpeshRating = (pegRatio, returnAlpha, croci, altmanZ) => {
  let rating = 5;
  
  if (pegRatio < 1.0) rating += 1.5;
  else if (pegRatio < 1.5) rating += 1;
  
  if (returnAlpha > 5) rating += 1.5;
  else if (returnAlpha > 0) rating += 1;
  
  if (croci > 15) rating += 1;
  else if (croci > 10) rating += 0.5;
  
  if (altmanZ > 3) rating += 0.5;
  
  return Math.min(Math.round(rating * 10) / 10, 9);
};

// Get sector for a ticker
const getSectorForTicker = (ticker) => {
  for (const [sector, tickers] of Object.entries(STOCK_DATA)) {
    if (tickers.includes(ticker) || tickers.includes(ticker.replace('-', '.'))) {
      return sector;
    }
  }
  return 'Other';
};

// Transform backend data to our schema
const transformBackendData = (stock) => {
  const pegRatio = stock.pegRatio || 1.5;
  const croci = Math.random() * 20 + 5; // CROCI not available in yfinance
  const returnAlpha = (stock.priceChange6m - 10) / 2; // Estimate alpha relative to market
  const volatility = (stock.beta || 1.0) * 20;
  const altmanZ = Math.random() * 5 + 1; // Altman Z not available in yfinance
  
  const alpeshRating = calculateAlpeshRating(pegRatio, returnAlpha, croci, altmanZ);
  const sector = stock.sector !== 'Unknown' ? mapYahooSector(stock.sector) : getSectorForTicker(stock.ticker);
  
  return {
    ticker: stock.ticker,
    name: stock.name,
    price: stock.price,
    marketCap: stock.marketCap,
    alpeshRating,
    croci,
    pegRatio,
    returnAlpha,
    priceChange6m: stock.priceChange6m,
    volatility,
    altmanZ,
    priceHistory: stock.priceHistory.length > 0 ? stock.priceHistory : generatePriceHistory(stock.price),
    sector,
    ma200: stock.ma200,
  };
};

// Map Yahoo Finance sectors to our categories
const mapYahooSector = (yahooSector) => {
  const sectorMap = {
    'Technology': 'Technology',
    'Financial Services': 'Finance',
    'Financial': 'Finance',
    'Consumer Cyclical': 'Consumer',
    'Consumer Defensive': 'Consumer',
    'Healthcare': 'Healthcare',
    'Industrials': 'Industrial',
    'Energy': 'Energy',
    'Communication Services': 'Telecom',
    'Telecommunications': 'Telecom',
  };
  return sectorMap[yahooSector] || 'Other';
};

export const fetchStockData = async () => {
  try {
    // Fetch data from Yahoo Finance backend
    const apiData = await fetchYahooFinanceData();
    
    if (!apiData || apiData.length === 0) {
      console.warn('API call failed, using fallback data');
      return generateFallbackData();
    }
    
    // Transform API data
    return apiData.map(stock => transformBackendData(stock));
  } catch (error) {
    console.error('Error in fetchStockData:', error);
    return generateFallbackData();
  }
};

// Fallback data generator if API fails
const generateFallbackData = () => {
  return TICKERS.map(ticker => {
    const price = Math.random() * 400 + 50;
    const pegRatio = Math.random() * 2.5 + 0.3;
    const croci = Math.random() * 20 + 5;
    const returnAlpha = (Math.random() - 0.4) * 15;
    const altmanZ = Math.random() * 5 + 1;
    const sector = getSectorForTicker(ticker);
    
    return {
      ticker,
      name: `${ticker} Inc.`,
      price,
      marketCap: Math.random() * 2000 + 1,
      alpeshRating: calculateAlpeshRating(pegRatio, returnAlpha, croci, altmanZ),
      croci,
      pegRatio,
      returnAlpha,
      priceChange6m: (Math.random() - 0.3) * 40,
      volatility: Math.random() * 30 + 10,
      altmanZ,
      priceHistory: generatePriceHistory(price),
      sector,
      ma200: price * (0.95 + Math.random() * 0.1), // Estimate MA200 near current price
    };
  });
};
