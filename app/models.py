from typing import Optional
from sqlmodel import Field, SQLModel, create_engine, Session

class ChildProfile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str | None = Field(index=True)  # 🔗 Link ke session
    
    # Field wajib
    birth_date: str  # YYYY-MM-DD
    gender: str      # L atau P
    
    # Field opsional
    name: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    topic: str | None = None

class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str | None = Field(index=True)
    role: str
    content: str

sqlite_file_name = "parentease.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url, echo=False)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)