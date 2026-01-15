# Migration to Redis/RQ Job Queue

## Overview

The application has been migrated from PostgreSQL-based job queue to Redis/RQ for better performance and reliability. Redis is better suited for job queues and provides faster job processing.

## Changes Made

1. **New Redis-based Queue** (`jobs/redis_queue.py`)
   - Uses Redis with RQ (Redis Queue) library
   - Faster job processing
   - Better suited for background tasks

2. **New RQ Worker** (`worker_rq.py`)
   - Uses RQ worker instead of polling PostgreSQL
   - Automatically processes jobs from Redis queue
   - More efficient than polling

3. **Updated Queue Interface** (`jobs/queue.py`)
   - Now uses Redis instead of PostgreSQL
   - Same interface, different backend

4. **Docker Compose Updated**
   - Added Redis service
   - Updated worker to use `worker_rq.py`
   - Added Redis volume for persistence

## Setup

### Local Development

1. **Redis is already included in docker-compose.yml**
   - Redis service will start automatically
   - No additional setup needed

2. **Environment Variables**
   - `REDIS_URL` (optional, defaults to `redis://redis:6379/0`)
   - For local dev, defaults to `redis://localhost:6379/0`

3. **Start Services**
   ```bash
   docker-compose up -d
   ```
   
   This will start:
   - Redis service
   - Flask app
   - RQ Worker

### Production (Render)

1. **Add Redis Service**
   - Option 1: Use Render's Redis addon (free tier available)
   - Option 2: Use Upstash Redis (free tier, managed Redis)
   - Option 3: Use Redis Cloud (free tier available)

2. **Environment Variables**
   - Add `REDIS_URL` to your Render services (flask-app and worker)
   - Format: `redis://username:password@host:port/db`
   - Example: `redis://default:password@redis-12345.upstash.io:6379/0`

3. **Update Worker Command**
   - Change worker command from `python worker.py` to `python worker_rq.py`
   - Or update Dockerfile CMD if using Docker

## Benefits

✅ **Faster job processing** - Redis is optimized for queues  
✅ **More reliable** - RQ handles job failures and retries better  
✅ **Easier to scale** - Can run multiple workers easily  
✅ **Better monitoring** - RQ Dashboard available for monitoring  
✅ **Free tier available** - Many Redis providers offer free tiers  

## Migration from PostgreSQL Queue

If you were using the PostgreSQL queue:

1. **No data migration needed** - Old jobs table can be ignored
2. **Worker will automatically use Redis** - No code changes needed
3. **Jobs table in PostgreSQL** - Can be dropped or kept for reference

## Testing

1. **Start services:**
   ```bash
   docker-compose up -d
   ```

2. **Check Redis connection:**
   ```bash
   docker-compose exec flask-app python -c "from jobs.redis_queue import get_redis_client; r = get_redis_client(); print('Redis connected:', r.ping())"
   ```

3. **Check worker status:**
   ```bash
   docker-compose logs worker
   ```
   Should see: "🚀 RQ Worker {WORKER_ID} started"

4. **Upload a test file** and verify it processes correctly

## Troubleshooting

### Worker Not Processing Jobs

1. **Check Redis connection:**
   - Verify `REDIS_URL` is set correctly
   - Test Redis connection: `redis-cli -u $REDIS_URL ping`

2. **Check worker logs:**
   ```bash
   docker-compose logs worker
   ```

3. **Check Redis keys:**
   ```bash
   docker-compose exec redis redis-cli KEYS "*"
   ```

### Jobs Stuck in Queue

1. **Check worker is running:**
   - Verify worker service is running
   - Check worker logs for errors

2. **Check Redis is accessible:**
   - Verify Redis service is running
   - Check network connectivity

3. **Check job status:**
   - Use RQ Dashboard if available
   - Or query Redis directly

## Rollback

If needed to rollback to PostgreSQL queue:

1. Change `jobs/queue.py` to import from `pg_queue` instead of `redis_queue`
2. Change worker command back to `python worker.py`
3. Remove Redis service from docker-compose.yml (optional)

