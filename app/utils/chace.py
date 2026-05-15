import json
from app.core.redis_client import redis_client

# Prefix key agar tidak tabrakan dengan data lain di Redis
PROFILE_PREFIX = "parentease:profile:"

async def get_cached_profile(session_id: str) -> dict | None:
    """Ambil profil dari cache. Jika Redis down, return None (fallback ke DB)."""
    if not redis_client:
        return None
        
    try:
        key = f"{PROFILE_PREFIX}{session_id}"
        data = await redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        print(f"⚠️ Redis Get Error: {e}")
        return None

async def set_cached_profile(session_id: str, data: dict, expire_seconds: int = 3600):
    """Simpan profil ke cache dengan expiry 1 jam."""
    if not redis_client:
        return
        
    try:
        key = f"{PROFILE_PREFIX}{session_id}"
        # Simpan sebagai JSON string
        await redis_client.set(key, json.dumps(data), ex=expire_seconds)
    except Exception as e:
        print(f"⚠️ Redis Set Error: {e}")

async def delete_cached_profile(session_id: str):
    """Hapus cache saat data di-update."""
    if not redis_client:
        return
        
    try:
        key = f"{PROFILE_PREFIX}{session_id}"
        await redis_client.delete(key)
    except Exception as e:
        print(f"️ Redis Delete Error: {e}")