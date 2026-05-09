import os
import uuid
import json
from datetime import date
from dateutil.relativedelta import relativedelta
from redis.asyncio import Redis
from dotenv import load_dotenv
from app.utils.schemas import SessionCreate

load_dotenv()

redis_client = Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True
)

def calculate_age_months(tanggal_lahir: date | str) -> int:
    """Hitung usia bayi dalam bulan"""
    if isinstance(tanggal_lahir, str):
        tanggal_lahir = date.fromisoformat(tanggal_lahir)
    delta = relativedelta(date.today(), tanggal_lahir)
    return delta.years * 12 + delta.months

def build_system_prompt(context: dict) -> str:
    """Bangun system prompt dinamis"""
    age = calculate_age_months(context.get("tanggal_lahir", date.today()))
    nama = context.get("nama_anak", "si kecil")
    topik = context.get("topik", "umum")
    
    return f"""Kamu adalah ParentEase AI, asisten parenting berbasis evidence.

DATA BAYI:
- Nama: {nama}
- Tanggal Lahir: {context.get('tanggal_lahir')}
- Usia: {age} bulan
- Gender: {context.get('gender')}
- Topik Utama: {topik}

ATURAN:
1. Gunakan bahasa Indonesia hangat, empatik, dan ilmiah.
2. Sesuaikan saran dengan usia {age} bulan.
3. Jika pertanyaan medis/ASI/MPASI/vaksin, gunakan tool `search_medical_guidelines`.
4. Jika ada data berat & usia, gunakan `calculate_z_score`.
5. Jangan hallucinate. Sarankan konsultasi dokter jika gejala serius.
6. Tanggal hari ini: {date.today().isoformat()}
"""

async def create_session(payload: SessionCreate) -> tuple[str, str]:
    """Buat session_id + simpan context ke Redis"""
    session_id = str(uuid.uuid4())
    redis_key = f"session:{session_id}"
    
    # mode='json' auto-convert date → "YYYY-MM-DD"
    context_json = payload.context.model_dump(mode='json')
    
    await redis_client.setex(redis_key, 86400, json.dumps(context_json))
    
    return session_id, redis_key

async def get_session_context(session_id: str) -> dict | None:
    """Ambil context dari Redis"""
    data = await redis_client.get(f"session:{session_id}")
    return json.loads(data) if data else None