from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import get_settings


class Base(DeclarativeBase):
    pass


def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url)


def get_session_factory():
    engine = get_engine()
    return sessionmaker(bind=engine)


def get_session():
    SessionFactory = get_session_factory()
    return SessionFactory()
