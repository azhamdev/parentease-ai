import pathlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import HTMLResponse
from sqlmodel import Session
from pydantic import BaseModel
from scalar_fastapi import get_scalar_api_reference
from .models import create_db_and_tables, ChatMessage, ChildProfile, engine
from .agent import process_parent_query
from app.api.v1.endpoints import sessions
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select

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
def chat_endpoint(
    request: ChatRequest, 
    session: Session = Depends(get_session),
    x_session_id: str | None = Header(None, alias="X-Session-ID")
):
    try:
        # 1. Save user message with session_id
        user_msg = ChatMessage(
            role="user", 
            content=request.message, 
            session_id=x_session_id
        )
        session.add(user_msg)
        
        # 🆕 2. Ambil data anak dari database berdasarkan session_id
        child_data = None
        if x_session_id:
            statement = select(ChildProfile).where(
                ChildProfile.session_id == x_session_id
            )
            child_profile = session.exec(statement).first()
            
            if child_profile:
                # Convert SQLModel ke dict untuk agent
                child_data = child_profile.model_dump()
                print(f"✅ Child data found: {child_data}")  # Debug log
            else:
                print(f"⚠️ No child data found for session: {x_session_id}")
        
        # 3. Process via Agent DENGAN child_data
        result = process_parent_query(request.message, child_data)
        ai_response_text = result["response"]

        # 4. Save AI response with session_id
        ai_msg = ChatMessage(
            role="assistant", 
            content=ai_response_text, 
            session_id=x_session_id
        )
        session.add(ai_msg)
        session.commit()

        return {"response": ai_response_text, "sources": result["sources"]}

    except Exception as e:
        print(f"❌ Error in chat_endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
