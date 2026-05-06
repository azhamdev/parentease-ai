from typing import Optional, List
from sqlmodel import Field, SQLModel, create_engine, Session

class ChildProfile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    birth_date: str # simplified for example

class ChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    role: str # 'user' or 'assistant'
    content: str

# SQLite connection
sqlite_file_name = "parentease.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url, echo=False)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)