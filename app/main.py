# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel import Session
from pydantic import BaseModel
from scalar_fastapi import get_scalar_api_reference
from .models import create_db_and_tables, ChatMessage, engine
from .agent import process_parent_query


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="ParentEase AI Backend", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


def get_session():
    with Session(engine) as session:
        yield session


@app.get("/scalar", include_in_schema=False)
def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )


@app.post("/chat")
def chat_endpoint(request: ChatRequest, session: Session = Depends(get_session)):
    try:
        # 1. Save user message
        user_msg = ChatMessage(role="user", content=request.message)
        session.add(user_msg)

        # 2. Process via OpenAI SDK + Mistral Tools
        ai_response_text = process_parent_query(request.message)

        # 3. Save AI response
        ai_msg = ChatMessage(role="assistant", content=ai_response_text)
        session.add(ai_msg)
        session.commit()

        return {"response": ai_response_text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
