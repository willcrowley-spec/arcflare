"""Redis client utility. Legacy sync phase tracking has been replaced by SyncEventEmitter."""
import redis


def get_redis_client() -> redis.Redis:
    from app.core.config import get_settings
    return redis.from_url(get_settings().REDIS_URL, decode_responses=True)
