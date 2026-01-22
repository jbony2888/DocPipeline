#!/usr/bin/env python3
"""
Redis Queue (RQ) Worker for processing submissions in the background.
Uses Redis/RQ for job queue management.

Usage:
    python worker_rq.py
"""

import os
import sys
import logging
from rq import Worker, Queue
from jobs.redis_queue import get_redis_client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Worker ID (unique identifier for this worker instance)
# Include timestamp to avoid conflicts on restart
import time
WORKER_ID = os.environ.get("WORKER_ID", f"worker-{os.getpid()}-{int(time.time())}")

logger.info(f"🚀 RQ Worker {WORKER_ID} started")
logger.info("📊 Using Redis/RQ for job queue")
logger.info("⏳ Listening for jobs on 'submissions' queue...")
logger.info("Press Ctrl+C to stop.")

def main():
    """Main worker loop."""
    try:
        redis_client = get_redis_client()
        
        # Test Redis connection
        try:
            redis_client.ping()
            logger.info("✅ Connected to Redis successfully")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            logger.error("   Make sure Redis is running and REDIS_URL is set correctly")
            sys.exit(1)
        
        # Create queue
        queue = Queue("submissions", connection=redis_client)
        
        # Clean up any stale workers with same name before starting
        try:
            from rq.registry import StartedJobRegistry, FinishedJobRegistry, FailedJobRegistry
            Worker.all(connection=redis_client)  # This cleans up dead workers
            logger.info("🧹 Cleaned up stale workers")
        except Exception as e:
            logger.warning(f"⚠️  Could not clean stale workers: {e}")
        
        # Create and start worker (RQ 2.x doesn't need Connection context manager)
        worker = Worker([queue], connection=redis_client, name=WORKER_ID)
        logger.info(f"👷 Worker {WORKER_ID} ready to process jobs")
        worker.work()
            
    except KeyboardInterrupt:
        logger.info("\n🛑 Worker stopped by user")
    except Exception as e:
        logger.error(f"❌ Error starting worker: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    main()

