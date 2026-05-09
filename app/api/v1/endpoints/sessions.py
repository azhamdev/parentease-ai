from app.utils.schemas import SessionCreate
from fastapi import APIRouter, Depends, HTTPException
from app.services.agent.orchestrator import create_session

router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.post("/")
async def init_session(payload: SessionCreate):
    try:
        session_id, redis_key = await create_session(payload)
        return {"session_id": session_id, "status": "initialized"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Session init failed: {str(e)}")