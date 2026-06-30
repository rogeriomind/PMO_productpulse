import pytest

from app.database.connection import create_sqlite_memory_session


@pytest.fixture
def db():
    session = create_sqlite_memory_session()
    try:
        yield session
    finally:
        session.close()
