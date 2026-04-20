from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.storage.models import Base


def get_engine(settings: Settings | None = None):
    settings = settings or get_settings()
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(settings.database_url, connect_args=connect_args, future=True)


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(settings), expire_on_commit=False, future=True)


def init_db(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if settings.database_url.startswith("sqlite"):
        # paths like sqlite:///./data/app.db
        path = settings.database_url.replace("sqlite:///", "", 1)
        if path.startswith("./"):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    Base.metadata.create_all(get_engine(settings))


def session_scope(settings: Settings | None = None) -> Generator[Session, None, None]:
    factory = get_session_factory(settings)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
