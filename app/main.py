from app.utils.schemas import SessionListItem
import pathlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Header
from fastapi.responses import HTMLResponse
from sqlmodel import Session
from pydantic import BaseModel
from scalar_fastapi import get_scalar_api_reference
from .models import create_db_and_tables, ChatMessage, ChildProfile, engine
from app.api.v1.endpoints import sessions
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select, desc
from app.services.agent.streaming import stream_chat_response
from fastapi.responses import StreamingResponse

STATIC_DIR = pathlib.Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="ParentEase AI Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)


class ChatRequest(BaseModel):
    message: str


def get_session():
    with Session(engine) as session:
        yield session


@app.get("/", include_in_schema=False)
def serve_frontend():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.get("/scalar", include_in_schema=False)
def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )

@app.post("/chat")
async def chat_endpoint_streaming(
    request: ChatRequest, 
    session: Session = Depends(get_session),
    x_session_id: str | None = Header(None, alias="X-Session-ID")
):
    user_msg = ChatMessage(role="user", content=request.message, session_id=x_session_id)
    session.add(user_msg)
    session.commit()

    child_data = None
    if x_session_id:
        stmt = select(ChildProfile).where(ChildProfile.session_id == x_session_id)
        profile = session.exec(stmt).first()
        if profile: child_data = profile.model_dump()

    async def event_generator():
        full_response = ""
        try:
            async for token in stream_chat_response(user_message=request.message, child_context=child_data):
                # ✅ SKIP token kosong/null
                if not token or token.strip() == "":
                    continue
                    
                full_response += token
                yield f"data: {token}\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
        finally:
            # ✅ JANGAN save jika response kosong
            if full_response and full_response.strip():
                ai_msg = ChatMessage(role="assistant", content=full_response, session_id=x_session_id)
                session.add(ai_msg)
                session.commit()
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    )


@app.get("/sessions", response_model=list[SessionListItem])
def list_sessions(session: Session = Depends(get_session)):
    """Ambil semua session untuk sidebar riwayat chat."""
    stmt = select(ChildProfile).order_by(desc(ChildProfile.id))
    profiles = session.exec(stmt).all()
    
    results = []
    for p in profiles:
        # Ambil pesan terakhir untuk preview
        msg_stmt = select(ChatMessage).where(
            ChatMessage.session_id == p.session_id
        ).order_by(desc(ChatMessage.id)).limit(1)
        last_msg = session.exec(msg_stmt).first()
        
        preview = "Mulai percakapan baru"
        if last_msg:
            content = last_msg.content.strip()
            preview = content[:45] + ("..." if len(content) > 45 else "")
            
        results.append({
            "session_id": p.session_id,
            "child_name": p.name or "Anak Tanpa Nama",
            "last_message_preview": preview,
            "created_at": None  # Bisa diisi jika ada field created_at di DB
        })
    return results

@app.get("/sessions/{session_id}/messages")
def get_session_messages(session_id: str, session: Session = Depends(get_session)):
    """Ambil semua pesan untuk session tertentu."""
    stmt = select(ChatMessage).where(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.id)
    messages = session.exec(stmt).all()
    
    return [
        {"id": m.id, "role": m.role, "content": m.content}
        for m in messages
    ]