import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Position
from app.db.migrate import run_migrations


@pytest.fixture
def db_engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    run_migrations(engine)
    yield engine
    os.unlink(path)


@pytest.fixture
def session(db_engine):
    Session = sessionmaker(bind=db_engine)
    s = Session()
    yield s
    s.close()


@pytest.fixture
def sample_position(session):
    p = Position(
        symbol="00700",
        market="HK",
        name="腾讯",
        cost_price=300.0,
        quantity=100,
        watch_below=280.0,
        watch_above=400.0,
    )
    session.add(p)
    session.commit()
    return p
