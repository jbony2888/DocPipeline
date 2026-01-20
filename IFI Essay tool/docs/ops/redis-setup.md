# Redis/RQ Setup - Quick Start

## What Changed

✅ Switched from PostgreSQL job queue to Redis/RQ  
✅ More reliable job processing  
✅ Better suited for background tasks  
✅ Free tier available from many providers  

## Local Development (Docker)

**No changes needed!** Redis is included in `docker-compose.yml`:

```bash
docker-compose up -d
```

This automatically starts:
- Redis service
- Flask app
- RQ Worker (uses `worker_rq.py`)

## Production Setup (Render)

### Option 1: Upstash Redis (Recommended - Free Tier)

1. **Create Upstash Redis account:**
   - Go to https://upstash.com/
   - Create free account
   - Create Redis database
   - Copy the REST URL

2. **Add to Render:**
   - Go to your Render service
   - Environment → Add Environment Variable
   - Key: `REDIS_URL`
   - Value: Your Upstash Redis URL (e.g., `redis://default:password@redis-12345.upstash.io:6379/0`)

3. **Update Worker:**
   - Worker service should use command: `python worker_rq.py`
   - Make sure `REDIS_URL` is set in worker environment too

### Option 2: Render Redis Addon

1. **Add Redis addon in Render:**
   - Dashboard → Addons → Redis
   - Free tier available

2. **Environment variable is set automatically:**
   - Render automatically sets `REDIS_URL`
   - Just make sure worker service can access it

### Option 3: Redis Cloud (Free Tier)

1. **Create Redis Cloud account:**
   - Go to https://redis.com/try-free/
   - Create free database
   - Copy connection URL

2. **Add to Render:**
   - Same as Upstash steps above

## Verify Setup

### Check Redis Connection (Local)

```bash
docker-compose exec flask-app python -c "from jobs.redis_queue import get_redis_client; r = get_redis_client(); print('Redis connected:', r.ping())"
```

Should output: `Redis connected: True`

### Check Worker (Local)

```bash
docker-compose logs worker
```

Should see: `🚀 RQ Worker {WORKER_ID} started` and `✅ Connected to Redis successfully`

### Test Job Processing

1. Upload a file through the UI
2. Check worker logs: `docker-compose logs worker -f`
3. Should see job processing messages

## Environment Variables

### Required for Production
- `REDIS_URL` - Redis connection URL
  - Format: `redis://[username:password@]host:port[/db]`
  - Example: `redis://default:password@redis-12345.upstash.io:6379/0`

### Optional (has defaults)
- `REDIS_URL` defaults to `redis://redis:6379/0` in Docker
- `REDIS_URL` defaults to `redis://localhost:6379/0` locally

## Benefits

✅ **Faster** - Redis is optimized for queues  
✅ **More reliable** - Better error handling and retries  
✅ **Free tier** - Available from Upstash, Redis Cloud, etc.  
✅ **Better monitoring** - RQ Dashboard available  
✅ **Easier scaling** - Can run multiple workers easily  

## Troubleshooting

**Jobs stuck in queue:**
1. Check Redis is running: `redis-cli ping`
2. Check worker is running: `docker-compose ps worker`
3. Check worker logs: `docker-compose logs worker`

**Connection errors:**
1. Verify `REDIS_URL` is set correctly
2. Check Redis is accessible from your network
3. Verify credentials are correct

**Worker not starting:**
1. Check Redis connection first
2. Check worker logs for errors
3. Verify `REDIS_URL` is set in worker environment



