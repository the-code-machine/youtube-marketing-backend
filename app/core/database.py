import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = quote_plus(os.getenv("DB_PASSWORD"))
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Workers set this env var so they get a smaller, isolated pool
IS_WORKER = os.getenv("GLOSSOUR_WORKER_MODE", "false").lower() == "true"
 
if IS_WORKER:
    engine = create_engine(
        DATABASE_URL,
        pool_size=2,
        max_overflow=2,
        pool_timeout=20,
        pool_recycle=600,      # Workers are short-lived; recycle frequently
        pool_pre_ping=True,
        echo=False,
    )
    _statement_timeout_ms = 600_000   # 10 min — workers do heavy queries
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=3,           # 3 always-warm connections
        max_overflow=5,        # Burst to 8 under load
        pool_timeout=30,       # Never wait more than 30s for a connection
        pool_recycle=1800,     # Recycle after 30 min (avoids stale TCP)
        pool_pre_ping=True,    # Validate connection before every use
        echo=False,
    )
    _statement_timeout_ms = 30_000    # 30s — API queries must be fast
 
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
 
 
def get_db():
    """FastAPI dependency — always closes the session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
 
 
@event.listens_for(engine, "connect")
def _set_connection_settings(dbapi_conn, connection_record):
    """
    Applied to every new connection in the pool.
    - statement_timeout: kills runaway queries before they block other requests
    - lock_timeout: don't wait forever for a lock (fast-fail instead of hang)
    """
    cursor = dbapi_conn.cursor()
    cursor.execute(f"SET statement_timeout = {_statement_timeout_ms}")
    cursor.execute("SET lock_timeout = 5000")
    cursor.close()
 