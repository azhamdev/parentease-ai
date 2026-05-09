from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select
from app.models import engine, ChildProfile
from app.utils.schemas import SessionCreate
from app.services.agent.orchestrator import create_session

router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.post("/", status_code=201)
async def init_session(payload: SessionCreate):
    try:
        # 1. Simpan ke Redis (Async)
        session_id, _ = await create_session(payload)

        # 2. Prepare data untuk SQLite (map field names)
        ctx = payload.context.model_dump(mode='json')
        db_data = {
            "session_id": session_id,
            "birth_date": ctx["tanggal_lahir"], 
            "gender": ctx["gender"],
            "name": ctx.get("nama_anak"),
            "weight_kg": ctx.get("berat_badan_kg"),
            "height_cm": ctx.get("tinggi_badan_cm"),
            "topic": ctx.get("topik"),
        }

        # 3. Upsert ke SQLite
        with Session(engine) as db:
            statement = select(ChildProfile).where(ChildProfile.session_id == session_id)
            existing = db.exec(statement).first()

            if existing:
                # Update existing
                for key, value in db_data.items():
                    if key != "session_id":  # session_id adalah PK reference, jangan di-update
                        setattr(existing, key, value)
                db.add(existing)
            else:
                # Insert new
                new_profile = ChildProfile(**db_data)
                db.add(new_profile)
            
            db.commit()

        return {
            "session_id": session_id,
            "status": "initialized",
            "message": "Session berhasil dibuat"
        }
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))