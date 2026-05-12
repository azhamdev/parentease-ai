import os

from dotenv import load_dotenv
from sqlmodel import SQLModel, Session, create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./parentease.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

def create_db_and_tables():
    """Create all tables defined in SQLModel metadata."""
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)

def get_session():
    """
    FastAPI dependency untuk mendapatkan database session.
    
    Usage:
        def my_endpoint(db: Session = Depends(get_session)):
            ...
    """
    with Session(engine) as session:
        yield session
