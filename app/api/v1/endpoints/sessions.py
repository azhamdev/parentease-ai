# app/api/v1/endpoints/sessions.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, update
from datetime import datetime
from app.models import ChildProfile, ChatMessage
from app.database import get_session

router = APIRouter(tags=["sessions"])

@router.get("/sessions", response_model=list[dict])
async def list_sessions(db_session: Session = Depends(get_session)):
    """Ambil semua session untuk sidebar riwayat chat."""
    try:
        # ✅ FILTER: Hanya ambil yang belum dihapus
        stmt = (
            select(ChildProfile)
            .where(ChildProfile.is_deleted == False)
            .order_by(ChildProfile.created_at.desc())
        )
        profiles = db_session.exec(stmt).all()
        
        results = []
        for p in profiles:
            # ✅ FILTER: Hanya pesan user yang belum dihapus
            msg_stmt = (
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == p.session_id,
                    ChatMessage.role == "user",
                    ChatMessage.is_deleted == False
                )
                .order_by(ChatMessage.created_at.desc())
                .limit(1)
            )
            last_msg = db_session.exec(msg_stmt).first()
            
            preview = "Mulai percakapan baru"
            if last_msg:
                content = last_msg.content.strip()
                preview = content[:45] + ("..." if len(content) > 45 else "")
            
            results.append({
                "session_id": p.session_id,
                "child_name": p.name or "Anak Tanpa Nama",
                "last_message_preview": preview,
                "created_at": p.created_at.isoformat() if p.created_at else None
            })
        
        return results
    except Exception as e:
        import logging
        logging.error(f"Error listing sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    db_session: Session = Depends(get_session)
):
    """Ambil semua pesan untuk session tertentu."""
    try:
        # ✅ VERIFIKASI: Session harus ada & belum dihapus
        profile_stmt = select(ChildProfile).where(
            ChildProfile.session_id == session_id,
            ChildProfile.is_deleted == False
        )
        profile = db_session.exec(profile_stmt).first()
        
        if not profile:
            raise HTTPException(status_code=404, detail="Session tidak ditemukan atau sudah dihapus")
        
        # ✅ FILTER: Hanya pesan yang belum dihapus
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.is_deleted == False
            )
            .order_by(ChatMessage.created_at.asc())
        )
        
        messages = db_session.exec(stmt).all()
        
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None
            }
            for m in messages
        ]
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Error getting messages for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# ✅ ENDPOINT BARU: Soft Delete Session
@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db_session: Session = Depends(get_session)
):
    """
    Hapus session secara soft (data tetap ada di DB tapi ditandai deleted).
    - Profile anak ditandai is_deleted=True
    - Semua chat message terkait juga ditandai deleted
    """
    # 1. Cek apakah session ada & belum dihapus
    profile_stmt = select(ChildProfile).where(
        ChildProfile.session_id == session_id,
        ChildProfile.is_deleted == False
    )
    profile = db_session.exec(profile_stmt).first()
    
    if not profile:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan atau sudah dihapus")
    
    now = datetime.utcnow()
    
    # 2. Soft delete semua message terkait
    msg_update = (
        update(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .values(is_deleted=True, deleted_at=now)
    )
    db_session.exec(msg_update)
    
    # 3. Soft delete profile
    profile.is_deleted = True
    profile.deleted_at = now
    db_session.add(profile)
    
    db_session.commit()
    
    return {
        "message": "Session berhasil dihapus",
        "deleted_at": now.isoformat()
    }