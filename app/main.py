import pathlib
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from scalar_fastapi import get_scalar_api_reference
from .models import create_db_and_tables
from app.api.v1.endpoints import sessions
from app.api.v1.endpoints import child_profiles
from app.api.v1.endpoints import chat
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

STATIC_DIR = pathlib.Path(__file__).parent / "static"

async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="ParentEase AI Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"])
app.include_router(child_profiles.router, prefix="/api/v1", tags=["child-profiles"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])


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
