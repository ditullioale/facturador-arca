import os
from collections.abc import Iterator

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ARCA_MODE", "mock")
os.environ.setdefault("ARCA_CUIT", "20111111112")
os.environ.setdefault("FACTURADOR_ADMIN_TOKEN", "admin-test")
os.environ.setdefault("FACTURADOR_SECRET", "secreto-de-test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import StaticPool, create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def engine():
    motor = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(motor)
    yield motor
    Base.metadata.drop_all(motor)


@pytest.fixture()
def db_session(engine) -> Iterator[Session]:
    """Sesión contra la misma base que ve el cliente, para preparar datos en un test."""
    sesion = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield sesion
    finally:
        sesion.close()


@pytest.fixture()
def client(engine) -> Iterator[TestClient]:
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
