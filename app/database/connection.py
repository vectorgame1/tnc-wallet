from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings
class Base(DeclarativeBase): pass
kwargs = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=kwargs, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
def init_database():
    from app.database import models
    Base.metadata.create_all(bind=engine)
