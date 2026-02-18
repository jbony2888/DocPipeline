#!/usr/bin/env python3
"""
Redis Queue (RQ) Worker for processing submissions in the background.
Uses Redis/RQ for job queue management.

Usage:
    python worker_rq.py
"""

import os
import sys
import uuid
import logging
from rq import Worker, Queue
from jobs.redis_queue import get_redis_client

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Worker ID: use WORKER_ID env, else RENDER_INSTANCE_ID, else unique per-start (avoids
# "worker already exists" when Render restarts before old worker unregisters from Redis)
WORKER_ID = os.environ.get("WORKER_ID") or os.environ.get("RENDER_INSTANCE_ID") or f"worker-{uuid.uuid4().hex[:12]}"

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

