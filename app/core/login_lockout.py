"""Account lockout after repeated failed login attempts using Redis."""

import redis.asyncio as redis

from app.config import settings

_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 15 * 60  # 15 minutes

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _key(email: str) -> str:
    return f"login_lockout:{email}"


async def check_lockout(email: str) -> None:
    """Raise RateLimitError if the account is locked out."""
    from app.core.exceptions import RateLimitError

    r = _get_redis()
    attempts = await r.get(_key(email))
    if attempts is not None and int(attempts) >= _MAX_ATTEMPTS:
        ttl = await r.ttl(_key(email))
        minutes = max(1, ttl // 60)
        raise RateLimitError(
            f"Account temporarily locked due to too many failed login attempts. "
            f"Try again in {minutes} minute(s)."
        )


async def record_failed_attempt(email: str) -> None:
    """Increment the failed login counter."""
    r = _get_redis()
    key = _key(email)
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, _LOCKOUT_SECONDS)
    await pipe.execute()


async def clear_attempts(email: str) -> None:
    """Clear failed attempts on successful login."""
    r = _get_redis()
    await r.delete(_key(email))
