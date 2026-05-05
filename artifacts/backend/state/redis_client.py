"""
Redis client for state snapshots.
Connection is optional — if Redis is unavailable, operations are no-ops.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

_client = None


async def get_redis():
    """Return the Redis client, or None if unavailable."""
    global _client
    if _client is not None:
        return _client
    try:
        import redis.asyncio as aioredis  # type: ignore
        _client = aioredis.from_url(REDIS_URL, decode_responses=True)
        await _client.ping()
        return _client
    except Exception:
        return None


async def snapshot_state(key: str, state: dict[str, Any]) -> bool:
    """Save a state snapshot to Redis. Returns True if saved, False if Redis unavailable."""
    client = await get_redis()
    if client is None:
        return False
    try:
        await client.set(key, json.dumps(state), ex=3600)
        return True
    except Exception:
        return False


async def load_snapshot(key: str) -> Optional[dict[str, Any]]:
    """Load a state snapshot from Redis. Returns None if not found or unavailable."""
    client = await get_redis()
    if client is None:
        return None
    try:
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        return None


async def list_snapshots(prefix: str) -> list[str]:
    """List all snapshot keys with a given prefix."""
    client = await get_redis()
    if client is None:
        return []
    try:
        keys = await client.keys(f"{prefix}*")
        return keys
    except Exception:
        return []
