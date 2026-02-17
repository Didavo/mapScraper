"""
FastAPI Dependencies.
"""

from typing import Generator
from sqlalchemy.orm import Session

from src.models import get_session_factory


def get_db() -> Generator[Session, None, None]:
    """Dependency für Datenbank-Session."""
    SessionFactory = get_session_factory()
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()
