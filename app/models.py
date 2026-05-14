from datetime import date, datetime

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

class ChildProfile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str | None = Field(index=True)
    birth_date: date
    gender: str
    name: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    topic: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = Field(
        default=False, 
        sa_column_kwargs={"server_default": "false"}
    )
    deleted_at: datetime | None = Field(default=None)

class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str | None = Field(index=True)
    role: str
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = Field(
        default=False, 
        sa_column_kwargs={"server_default": "false"}
    )
    deleted_at: datetime | None = Field(default=None)

class VaccineRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    vaccine_code: str = Field(index=True)
    date_given: date | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ToolCall(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str | None = Field(default=None, index=True)
    tool_name: str = Field(index=True)
    status: str = Field(index=True)
    input_payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    output_payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    sources: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    filename: str = Field(index=True)
    source_type: str = Field(default="pdf", index=True)
    status: str = Field(default="completed", index=True)
    collection_name: str | None = Field(default=None, index=True)
    chunk_count: int = 0
    error_message: str | None = None
    ingested_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
