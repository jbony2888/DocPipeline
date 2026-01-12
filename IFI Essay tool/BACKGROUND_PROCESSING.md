# Background Processing Setup

This application uses **RQ (Redis Queue)** for background job processing. This allows handling hundreds of submissions without request timeouts.

## Architecture

- **Flask App**: Handles HTTP requests, enqueues jobs
- **Redis**: Job queue storage
- **RQ Workers**: Background processes that execute jobs

## Setup

### 1. Install Redis

**Local Development:**
```bash
# macOS
brew install redis
brew services start redis

# Linux
sudo apt-get install redis-server
sudo systemctl start redis
```

**Docker:**
Redis is included in `docker-compose.yml`

### 2. Start Worker

Run the worker in a separate terminal:

```bash
python worker.py
```

Or with Docker:
```bash
docker-compose up worker
```

### 3. Environment Variables

Add to your `.env` or environment:
```bash
REDIS_URL=redis://localhost:6379/0
```

## How It Works

1. **User uploads files** → Flask app enqueues jobs to Redis
2. **Worker picks up jobs** → Processes submissions in background
3. **Frontend polls progress** → Shows real-time updates every 2 seconds
4. **Jobs complete** → Results saved to database, UI updates

## Processing 500 Submissions

### Performance Estimates

- **Average time per file**: 10-15 seconds
- **500 files**: ~100-125 minutes (1.5-2 hours)
- **With 4 workers**: ~25-30 minutes

### Scaling Workers

Run multiple workers for parallel processing:

```bash
# Terminal 1
python worker.py

# Terminal 2
python worker.py

# Terminal 3
python worker.py

# Terminal 4
python worker.py
```

Or with Docker Compose, scale workers:
```bash
docker-compose up --scale worker=4
```

### Monitoring

Check job queue status:
```python
from jobs.queue import job_queue
print(f"Queue length: {len(job_queue)}")
```

## API Endpoints

- `POST /upload` - Enqueue files for processing
- `GET /api/batch_status` - Get progress of all jobs
- `GET /api/job_status/<job_id>` - Get status of single job

## Troubleshooting

**Jobs not processing:**
- Check Redis is running: `redis-cli ping` (should return `PONG`)
- Check worker is running: Look for "Worker started" message
- Check logs: `docker-compose logs worker`

**Jobs failing:**
- Check worker logs for errors
- Verify API keys (GROQ_API_KEY, GOOGLE_APPLICATION_CREDENTIALS)
- Check Supabase connection

**Progress not updating:**
- Check browser console for errors
- Verify `/api/batch_status` endpoint returns data
- Check session has `processing_jobs` stored



