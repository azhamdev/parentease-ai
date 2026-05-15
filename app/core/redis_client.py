# app/core/redis_client.py
import os
import redis.asyncio as redis
import logging

logger = logging.getLogger(__name__)

# Build URL fleksibel
REDIS_URL = os.getenv("REDIS_URL") or f"redis://{os.getenv('REDIS_HOST', 'localhost')}:{os.getenv('REDIS_PORT', '6379')}/{os.getenv('REDIS_DB', '0')}"

# Deklarasi global dengan type hint yang tepat
redis_client: redis.Redis | None = None

async def init_redis():
    global redis_client
    try:
        # redis.from_url lebih stabil daripada constructor manual
        redis_client = redis.from_url(
            REDIS_URL,
            decode_responses=True
        )
        
        # ✅ FIX: Tambah type ignore untuk menghindari error type checker
        # ping() di redis-py async selalu return Awaitable, tapi type stubs kadang tidak akurat
        await redis_client.ping()  # type: ignore[misc]
        logger.info("✅ Redis connected successfully")
        
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        redis_client = None

async def close_redis():
    global redis_client
    if redis_client:
        try:
            # redis-py v5+ menggunakan aclose(), v4 menggunakan close()
            if hasattr(redis_client, 'aclose'):
                await redis_client.aclose()
            else:
                await redis_client.close()  # type: ignore[misc]
            logger.info("🔌 Redis connection closed")
        except Exception as e:
            logger.error(f"⚠️ Error closing Redis connection: {e}")
        finally:
            redis_client = None