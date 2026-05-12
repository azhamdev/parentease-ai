from sqlmodel import SQLModel, create_engine, Session

DATABASE_URL = "sqlite:///./parentease.db"
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})

def create_db_and_tables():
    """Create all tables defined in SQLModel metadata."""
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