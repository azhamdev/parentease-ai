import uuid
import json
from app.utils.schemas import SessionCreate
import os
from redis.asyncio import Redis
from dotenv import load_dotenv

load_dotenv()  # Load variabel dari .env

# Fallback ke localhost jika env var tidak diset
redis_client = Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True
)

async def create_session(payload: SessionCreate) -> tuple[str, str]:
    session_id = str(uuid.uuid4())
    redis_key = f"session:{session_id}"
    
    # mode='json' mengubah date -> string "YYYY-MM-DD" secara otomatis
    context_dict = payload.context.model_dump(mode='json')
    
    # TTL 24 jam (86400 detik)
    await redis_client.setex(redis_key, 86400, json.dumps(context_dict))
    
    return session_id, redis_key