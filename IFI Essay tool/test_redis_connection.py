#!/usr/bin/env python3
"""
Quick test script to verify Redis connection.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from jobs.redis_queue import get_redis_client
    
    print("🧪 Testing Redis connection...")
    print(f"📡 REDIS_URL: {os.environ.get('REDIS_URL', 'NOT SET')[:50]}...")
    print()
    
    redis_client = get_redis_client()
    
    # Test ping
    if redis_client.ping():
        print("✅ Redis connected successfully!")
        
        # Get Redis info
        info = redis_client.info('server')
        print(f"✅ Redis version: {info.get('redis_version', 'unknown')}")
        
        # Test queue
        from jobs.redis_queue import get_queue
        queue = get_queue()
        print(f"✅ Queue initialized: {queue.name}")
        
        print()
        print("✅ All Redis tests passed!")
        sys.exit(0)
    else:
        print("❌ Redis ping failed")
        sys.exit(1)
        
except Exception as e:
    print(f"❌ Error connecting to Redis: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

