import os
from sqlalchemy import create_engine
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


engine = create_engine(
    DATABASE_URL,
    # ── Pool settings for 4 GB RAM ───────────────────────────────────────────
    pool_size=5,          # idle connections kept alive
    max_overflow=10,      # extra connections allowed under load (total max = 15)
    pool_timeout=30,      # raise error if no connection available after 30 s
    pool_recycle=1800,    # recycle connection after 30 min (avoids stale TCP)
    pool_pre_ping=True,   # validate connection health before use

    # ── Query performance ────────────────────────────────────────────────────
    # Tells Postgres to return rows as soon as they're available (streaming)
    # rather than buffering the entire result set in memory.
    execution_options={"stream_results": True},

    # ── Misc ─────────────────────────────────────────────────────────────────
    echo=False,           # Set True temporarily to debug slow queries
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()