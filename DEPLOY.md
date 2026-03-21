# Deployment Guide — 24/7 Trading Signals on Railway

## Quick Start (5 minutes)

### 1. Create Railway Account
- Go to https://railway.app
- Sign up (free tier includes $5/month credits)

### 2. Connect GitHub
- Railway → GitHub → authorize
- Or use Railway CLI: `railway login`

### 3. Deploy
```bash
# Option A: Via GitHub (recommended)
# Push to GitHub, Railway auto-deploys on push
git push origin main

# Option B: Via CLI
railway init          # Link to Railway project
railway up            # Deploy immediately
```

### 4. Configure Services
In Railway dashboard:

**PostgreSQL (Database)**
- Add service → PostgreSQL
- Railway auto-injects `DATABASE_URL`

**Redis (Caching/Celery)**
- Add service → Redis
- Railway auto-injects `REDIS_URL`

**Web Service (Your app)**
- Already deployed from Dockerfile
- Auto-restarts on crash (configured in `railway.json`)
- Healthcheck at `/health` every 30s

### 5. Set Environment Variables
In Railway → Variables:
```
EXCHANGE_ID=bybit              # (binance blocked on Railway US IPs)
EXCHANGE_API_KEY=your_key
EXCHANGE_API_SECRET=your_secret
EXCHANGE_SANDBOX=true          # Keep true until ready for real money!
LOG_LEVEL=INFO
MAX_WORKERS=4
MAX_STRATEGIES=10
PORT=8000                       # Railway assigns automatically
```

### 6. Access Your Dashboard
```
https://YOUR_PROJECT.up.railway.app/ui
```

## How It Works

### Auto-Recovery
- **Healthcheck**: Railway pings `/health` every 30s
- **Restart Policy**: If unhealthy, restarts automatically (max 3 retries)
- **Signal Engine**: Catches errors, backoff retries, logs everything
- **Database**: Persists to PostgreSQL (survives restarts)

### Monitoring
1. **Logs** → See real-time logs in Railway dashboard
2. **Logs tab** in `/ui` → Live system activity
3. **Health endpoint** → `/health` shows DB/exchange/strategies status

### Scaling Up
```bash
# Increase workers if needed
railway variables set MAX_WORKERS=8

# Deploy multiple instances
railway service scale WEB=2   # 2 concurrent instances
```

## Troubleshooting

### App keeps restarting?
1. Check logs: Railway dashboard → Logs
2. Check `/health` endpoint directly
3. Verify environment variables are set
4. Check `EXCHANGE_SANDBOX=true` (don't use real money yet)

### Data not persisting?
- Ensure PostgreSQL service is connected
- Check `DATABASE_URL` is auto-injected (Railway does this)
- Verify DB migrations ran on startup

### Slow or timing out?
- Increase `MAX_WORKERS` (Railway will charge accordingly)
- Check exchange rate limits (may need API keys with higher limits)
- Reduce number of strategies or timeframes

### Getting blocked by Binance?
- Already handled: auto-fallback to Bybit/OKX/KuCoin
- Check logs for "geo-blocked" → it auto-switches exchanges

## Costs

**Free tier (~$5/month credits):**
- Web service: ~2GB RAM = $7/month
- PostgreSQL: ~500MB = $15/month
- Redis: ~256MB = $7/month
- **Covered by free credits for first month**

**After free credits:**
- Scale down to single instance + shared DB = ~$15-20/month
- Or use Railway's free tier limits

## Advanced: Local Testing

Before deploying to Railway:

```bash
# Install dependencies
pip install -e .

# Run tests
pytest tests/

# Run locally (like Railway will)
docker build -t crypto-mega .
docker run -e PORT=8000 -p 8000:8000 crypto-mega

# Or directly
uvicorn crypto_mega.api.app:app --host 0.0.0.0 --port 8000
```

## CI/CD Pipeline

Railway automatically:
1. Detects `Dockerfile`
2. Builds image
3. Runs healthcheck
4. Routes traffic only when healthy
5. Keeps previous version running during deploy (zero-downtime)

## Rolling Back

If something breaks:
```bash
railway rollback          # Go to previous version
```

Or via Railway dashboard → Deployments → click previous version

---

**Status**: Ready for 24/7 trading. All systems resilient to crashes and network failures.
