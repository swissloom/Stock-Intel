# Stock Market Intelligence Dashboard

A desktop stock market dashboard with Apple's "Liquid Glass" design language, built with React and Tailwind CSS.

## Features

- **Liquid Glass UI**: High-transparency panels with backdrop blur, subtle borders, and refractive shadows
- **Dynamic Mesh Gradient**: Slow-moving deep blue/purple gradient background
- **Real-time Stock Data**: Tracks stocks with Market Cap > $1B from NASDAQ/S&P 500
- **Financial Metrics**: Alpesh Rating, CROCI %, PEG Ratio, Return Alpha, Price Changes, Volatility, Altman-Z Score
- **Signal Detection**: Flashing green glow when stocks hit Alpesh 9 rating + positive alpha + PEG < 1.0
- **Smart Filtering**: Top Rated, High Growth, and High CROCI views
- **Glass-morphic Search**: Real-time search across tickers and company names

## Installation

```bash
npm install
```

## Development

```bash
npm run dev
```

## Production Build

```bash
npm run build
npm run preview
```

## API Integration

The app is integrated with Yahoo Finance via RapidAPI. The API key is already configured in `src/services/stockService.js`.

If the API fails or rate limits are hit, the app automatically falls back to generated data to ensure continuous operation.

To use your own API key:
1. Get a key from [RapidAPI Yahoo Finance](https://rapidapi.com/enclout-enclout-default/api/enclout-yahoo-finance)
2. Update the `RAPIDAPI_KEY` constant in `src/services/stockService.js`

## Tech Stack

- React 18
- Vite
- Tailwind CSS
- Recharts (for sparklines)
