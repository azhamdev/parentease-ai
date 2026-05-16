# tests/test_redis_cache.py
import asyncio
import os
import sys
from dotenv import load_dotenv

# Setup path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, root_dir)
load_dotenv(os.path.join(root_dir, '.env'))

# ✅ Import modul untuk akses redis_client
from app.core import redis_client as redis_mod
from app.core.redis_client import init_redis, close_redis
# Import helper cache
from app.utils.cache import get_cached_profile, set_cached_profile, delete_cached_profile

async def test_cache_logic():
    print("\n🔍 Testing Redis Cache Logic (Profile)...")
    
    # 1. Init Redis - WAJIB dipanggil dulu
    print("🔄 Initializing Redis...")
    await init_redis()
    
    # Verifikasi Redis client sudah ter-set di modul
    print(f"🔍 Redis client status: {redis_mod.redis_client}")
    
    if not redis_mod.redis_client:
        print("❌ FAILED: Redis client is None after init")
        return False
    
    test_session_id = "test-cache-123"

    try:
        # 2. Test GET (Sebelumnya kosong, harus None)
        print("\n📉 Testing GET (Empty)...")
        result = await get_cached_profile(test_session_id)
        if result is not None:
            print(f"❌ Expected None, got {result}")
            return False
        print("✅ GET Empty: Success")

        # 3. Test SET (Simpan data profil)
        print("\n💾 Testing SET (Save Profile)...")
        dummy_profile = {
            "session_id": test_session_id,
            "name": "Anak Test",
            "birth_date": "2024-01-01",
            "gender": "L",
            "weight_kg": 10.5
        }
        
        # Direct test dengan Redis client untuk verifikasi
        print("🔍 Direct Redis test...")
        await redis_mod.redis_client.set(f"parentease:profile:{test_session_id}", '{"direct": "test"}', ex=10)
        direct_get = await redis_mod.redis_client.get(f"parentease:profile:{test_session_id}")
        print(f"Direct GET result: {direct_get}")
        
        # Test via cache helper
        await set_cached_profile(test_session_id, dummy_profile)
        print("✅ SET Profile: Success")

        # 4. Test GET (Harusnya ada datanya)
        print("\n📈 Testing GET (After Set)...")
        
        # Cek langsung dari Redis
        direct_check = await redis_mod.redis_client.get(f"parentease:profile:{test_session_id}")
        print(f"Direct Redis check: {direct_check}")
        
        # Cek via helper
        cached_data = await get_cached_profile(test_session_id)
        print(f"Cached data result: {cached_data}")
        
        if not cached_data or cached_data.get("name") != "Anak Test":
            print(f"❌ Cache miss or wrong data: {cached_data}")
            return False
        print(f"✅ GET Cached: Success (Name: {cached_data['name']})")

        # 5. Test DELETE (Invalidation saat Update)
        print("\n🗑️ Testing DELETE (Invalidation)...")
        await delete_cached_profile(test_session_id)
        print("✅ DELETE Cache: Success")

        # 6. Test GET (Setelah delete, harus None lagi)
        print("\n📉 Testing GET (After Delete)...")
        result_after_delete = await get_cached_profile(test_session_id)
        if result_after_delete is not None:
            print("❌ Data masih ada setelah dihapus!")
            return False
        print("✅ GET After Delete: Success (Data purged)")

        print("\n🎉 ALL CACHE LOGIC TESTS PASSED!")
        return True

    except Exception as e:
        print(f"❌ Error during cache test: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await close_redis()

if __name__ == "__main__":
    success = asyncio.run(test_cache_logic())
    sys.exit(0 if success else 1)