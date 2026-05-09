# main.py
import pathlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel import Session
from pydantic import BaseModel
from scalar_fastapi import get_scalar_api_reference
from .models import create_db_and_tables, ChatMessage, engine
from .agent import process_parent_query
from .tools.schemas import VaccineScheduleRequest, VaccineScheduleResponse
from .tools.vaccine_schedule import calculate_vaccine_schedule

STATIC_DIR = pathlib.Path(__file__).parent / "static"


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
def chat_endpoint(request: ChatRequest, session: Session = Depends(get_session)):
    try:
        # 1. Save user message
        user_msg = ChatMessage(role="user", content=request.message)
        session.add(user_msg)

        # 2. Process via OpenAI SDK + Mistral Tools
        result = process_parent_query(request.message)
        ai_response_text = result["response"]

        # 3. Save AI response
        ai_msg = ChatMessage(role="assistant", content=ai_response_text)
        session.add(ai_msg)
        session.commit()

        return {"response": ai_response_text, "sources": result["sources"]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tools/vaccine-schedule", response_model=VaccineScheduleResponse)
def vaccine_schedule_endpoint(request: VaccineScheduleRequest):
    return calculate_vaccine_schedule(request)
