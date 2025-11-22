import os
from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine
from sqlalchemy.orm import sessionmaker

# Load environment from .env if present
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("db_url") or os.getenv("DB_URL")

# Helper to strip wrapping quotes and whitespace
def _clean_db_url(url: str) -> str:
    if not url:
        return url
    url = url.strip()
    if (url.startswith('"') and url.endswith('"')) or (url.startswith("'") and url.endswith("'")):
        url = url[1:-1]
    return url.strip()

DATABASE_URL = _clean_db_url(DATABASE_URL)

# If DATABASE_URL is provided, attempt to use it; otherwise use a local sqlite fallback
_engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        _engine = create_engine(DATABASE_URL, echo=False)
        # Try a lightweight connection test (will raise on DNS/connect failures)
        with _engine.connect() as conn:
            pass
    except Exception as e:
        # Remote DB is unreachable (DNS/network/credentials); fall back to local sqlite for dev
        print(f"Warning: could not connect to DATABASE_URL, falling back to local sqlite. Error: {e}")
        _engine = create_engine("sqlite:///./edu_path_local.db", echo=False)
else:
    # No DATABASE_URL set; use local sqlite for development
    print("No DATABASE_URL found in environment; using local sqlite ./edu_path_local.db")
    _engine = create_engine("sqlite:///./edu_path_local.db", echo=False)

SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def init_db():
    """Create database tables; if creation against the configured engine fails, emit a warning but don't crash the app."""
    try:
        SQLModel.metadata.create_all(_engine)
    except Exception as e:
        # In production you'd log this to your observability system. For now, print.
        print(f"Warning: init_db failed: {e}")


def get_session():
    """Yields a SQLAlchemy Session for dependency injection."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# Expose engine for other modules that import this file
engine = _engine
