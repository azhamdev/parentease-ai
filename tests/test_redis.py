import asyncio
import os
import sys
from dotenv import load_dotenv

# ✅ 1. Setup path & load .env
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, root_dir)
load_dotenv(os.path.join(root_dir, '.env'))

# ✅ 2. IMPORT MODUL (BUKAN VARIABEL LANGSUNG)
# Ini wajib agar perubahan global variable terdeteksi setelah init_redis() dipanggil
from app.core import redis_client as redis_mod
from app.core.redis_client import init_redis, close_redis

async def test_redis():
    print("🔍 Testing Redis Connection...")

    # 1. Init Redis
    await init_redis()

    # ✅ 3. CEK VIA MODUL ATTRIBUTE
    if not redis_mod.redis_client:
        print("❌ FAILED: Redis client is None")
        return False
    
    client = redis_mod.redis_client

    # 2. Test PING
    try:
        pong = await client.ping()
        print(f"✅ PING Test: {'PONG' if pong else 'NO PONG'}")
    except Exception as e:
        print(f"❌ PING Test Failed: {e}")
        return False

    # 3. Test SET & GET
    try:
        await client.set("test:parentease", "success", ex=10)
        val = await client.get("test:parentease")
        if val == "success":
            print("✅ SET/GET Test: Success")
        else:
            print(f"❌ SET/GET Test Failed: Expected 'success', got '{val}'")
            return False
    except Exception as e:
        print(f"❌ SET/GET Test Failed: {e}")
        return False

    print("\n🎉 ALL TESTS PASSED! Redis berjalan dengan sempurna.")
    await close_redis()
    return True

if __name__ == "__main__":
    success = asyncio.run(test_redis())
    sys.exit(0 if success else 1)