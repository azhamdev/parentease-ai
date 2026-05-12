from datetime import date
from datetime import datetime

from sqlmodel import Field, SQLModel


class ChildProfile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str | None = Field(index=True)  # 🔗 Link ke session
    
    # Field wajib
    birth_date: date  # YYYY-MM-DD
    gender: str      # L atau P
    
    # Field opsional
    name: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    topic: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str | None = Field(index=True)
    role: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class VaccineRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    vaccine_code: str = Field(index=True)
    date_given: date | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
