import asyncio
import json
from datetime import date
from app.src.utils.schemas import WelcomeContext, SessionCreate
from app.src.services.agent.orchestrator import create_session
import redis.asyncio as redis

async def main():
    # ✅ TEST 1: Hanya field wajib
    ctx_minimal = WelcomeContext(tanggal_lahir=date(2024, 5, 15), gender="L")
    print("✅ Minimal schema valid:", ctx_minimal.model_dump(mode='json'))

    # ✅ TEST 2: Lengkap + opsional
    ctx_full = WelcomeContext(
        tanggal_lahir=date(2023, 11, 20),
        gender="P",
        nama_anak="Aisyah",
        berat_badan_kg=8.2,
        tinggi_badan_cm=72.5,
        topik="MPASI"
    )
    print("✅ Full schema valid:", ctx_full.model_dump(mode='json'))

    # ✅ TEST 3: Redis & Session Creation
    payload = SessionCreate(context=ctx_full)
    session_id, key = await create_session(payload)
    print(f"\n✅ Session created: {session_id}")
    
    r = redis.from_url("redis://localhost:6379/0", decode_responses=True)
    cached = await r.get(key)
    data = json.loads(cached)
    
    print("✅ Redis cache verified:")
    print(f"   - Tanggal Lahir: {data['tanggal_lahir']} (type: {type(data['tanggal_lahir']).__name__})")
    print(f"   - Gender: {data['gender']}")
    print(f"   - Nama Anak: {data.get('nama_anak')}")
    print(f"   - Topik: {data.get('topik')}")

asyncio.run(main())