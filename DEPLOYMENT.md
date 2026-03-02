# Deployment Guide

## Quick Deploy (Recommended)

### Option 1: Vercel (Frontend) + Railway (Backend)

#### Deploy Backend to Railway:
1. Create account: https://railway.app
2. Click "New Project" → "Deploy from GitHub"
3. Select your repo
4. Add environment variables:
   - `FINNHUB_API_KEY`: d6hdsc9r01qnjncoai80d6hdsc9r01qnjncoai8g
   - `ALPHA_VANTAGE_API_KEY`: RCRJKNJ6K490DDML
5. Railway auto-detects Python and deploys
6. Copy your Railway URL (e.g., `https://your-app.railway.app`)

#### Deploy Frontend to Vercel:
1. Create account: https://vercel.com
2. Install Vercel CLI: `npm install -g vercel`
3. Update `vercel.json` with your Railway URL
4. Run: `vercel`
5. Done! Your dashboard is live globally

**Total Time**: 10 minutes
**Cost**: Free (Railway gives $5 credit)

---

### Option 2: All-in-One on Render

1. Create account: https://render.com
2. Create "Web Service" for backend:
   - Build Command: `pip install -r server/requirements-prod.txt`
   - Start Command: `cd server && gunicorn server:app`
3. Create "Static Site" for frontend:
   - Build Command: `npm install && npm run build`
   - Publish Directory: `dist`
4. Update frontend API URL to point to backend

**Total Time**: 15 minutes
**Cost**: Free tier available

---

### Option 3: DigitalOcean App Platform

1. Create account: https://www.digitalocean.com
2. Click "Create" → "Apps"
3. Connect GitHub repo
4. Configure:
   - Frontend: Node.js (auto-detected)
   - Backend: Python (auto-detected)
5. Add environment variables
6. Deploy

**Total Time**: 20 minutes
**Cost**: $5/month

---

## Performance Improvements

### Add Redis Caching (Railway)

1. In Railway, add Redis service
2. Update `server/server.py`:

```python
import redis
import json

# Connect to Redis
redis_client = redis.from_url(os.getenv('REDIS_URL'))

@app.route('/api/stocks', methods=['GET'])
def get_stocks():
    # Check cache first
    cached = redis_client.get('stocks_data')
    if cached:
        return jsonify(json.loads(cached))
    
    # Fetch fresh data
    stocks_data = fetch_stocks()
    
    # Cache for 5 minutes
    redis_client.setex('stocks_data', 300, json.dumps(stocks_data))
    
    return jsonify(stocks_data)
```

### Enable Compression

Add to `server/server.py`:
```python
from flask_compress import Compress

app = Flask(__name__)
Compress(app)
```

---

## Speed Comparison

| Hosting | Load Time | Monthly Cost | Setup Time |
|---------|-----------|--------------|------------|
| Localhost | 2-3s | $0 | 0 min |
| Vercel + Railway | 0.5-1s | $0-5 | 10 min |
| Render | 1-2s | $0 | 15 min |
| DigitalOcean | 0.8-1.5s | $5 | 20 min |
| AWS | 0.5-1s | $10-20 | 60 min |

---

## Recommended Stack

**For Best Performance:**
- **Frontend**: Vercel (Global CDN, instant deploys)
- **Backend**: Railway (Python support, Redis included)
- **Caching**: Redis on Railway
- **Total Cost**: $0-5/month
- **Speed**: 3-5x faster than localhost

---

## Next Steps

1. Push code to GitHub
2. Deploy backend to Railway
3. Deploy frontend to Vercel
4. Add Redis caching
5. Enable auto-deploy on push

Your dashboard will be:
- ✅ Accessible from anywhere
- ✅ 3-5x faster
- ✅ Auto-updating
- ✅ Professional URL
- ✅ SSL/HTTPS enabled
