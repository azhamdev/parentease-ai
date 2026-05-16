# app/utils/cache.py
import json
from app.core import redis_client as redis_module  # ✅ Import modul, bukan variabel

# Prefix key agar tidak tabrakan dengan data lain di Redis
PROFILE_PREFIX = "parentease:profile:"

async def get_cached_profile(session_id: str) -> dict | None:
    """Ambil profil dari cache. Jika Redis down, return None (fallback ke DB)."""
    # ✅ Akses redis_client dari modul (bukan import langsung)
    client = redis_module.redis_client
    
    if not client:
        # print("⚠️ Redis client is None in get_cached_profile")
        return None
        
    try:
        key = f"{PROFILE_PREFIX}{session_id}"
        data = await client.get(key)
        
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        print(f"⚠️ Redis Get Error: {e}")
        return None

async def set_cached_profile(session_id: str, data: dict, expire_seconds: int = 3600):
    """Simpan profil ke cache dengan expiry 1 jam."""
    # ✅ Akses redis_client dari modul
    client = redis_module.redis_client
    
    if not client:
        # print("⚠️ Redis client is None in set_cached_profile")
        return
        
    try:
        key = f"{PROFILE_PREFIX}{session_id}"
        await client.set(key, json.dumps(data), ex=expire_seconds)
    except Exception as e:
        print(f"⚠️ Redis Set Error: {e}")

async def delete_cached_profile(session_id: str):
    """Hapus cache saat data di-update."""
    # ✅ Akses redis_client dari modul
    client = redis_module.redis_client
    
    if not client:
        # print("⚠️ Redis client is None in delete_cached_profile")
        return
        
    try:
        key = f"{PROFILE_PREFIX}{session_id}"
        await client.delete(key)
    except Exception as e:
        print(f"⚠️ Redis Delete Error: {e}")