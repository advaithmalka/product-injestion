from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def make_session_factory(database_url: str):
    return sessionmaker(bind=make_engine(database_url), expire_on_commit=False)


def initialize_database(database_url: str):
    from marketplace import models  # noqa: F401

    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


def session_scope(database_url: str):
    """Return a configured Session context manager for short-lived operations."""
    return make_session_factory(database_url)()
