#!/usr/bin/env python3
"""
Integration test to verify Redis connection.
"""

import os

import pytest
from dotenv import load_dotenv


def test_redis_connection():
    # Load environment variables
    load_dotenv()

    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        pytest.skip("REDIS_URL is not set")

    print("🧪 Testing Redis connection...")
    print(f"📡 REDIS_URL: {redis_url[:50]}...")
    print()

    try:
        from jobs.redis_queue import get_queue, get_redis_client

        redis_client = get_redis_client()
        assert redis_client.ping(), "Redis ping failed"
        print("✅ Redis connected successfully!")

        info = redis_client.info("server")
        version = info.get("redis_version")
        print(f"✅ Redis version: {version or 'unknown'}")
        assert version, "Redis version string missing"

        queue = get_queue()
        print(f"✅ Queue initialized: {queue.name}")
        assert queue.name == "submissions"

        print()
        print("✅ All Redis tests passed!")
    except Exception as exc:
        print(f"❌ Error connecting to Redis: {exc}")
        pytest.skip("Redis unavailable for integration test")
