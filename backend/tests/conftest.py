from __future__ import annotations

import os
import sys
from pathlib import Path

# Asegura que "app" sea importable al correr `pytest` desde backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("STT_PROVIDER", "mock")
os.environ.setdefault("TTS_PROVIDER", "mock")
os.environ.setdefault("SMART_HOME_PROVIDER", "mock")
os.environ.setdefault("VISION_PROVIDER", "mock")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ATLAS_PASSWORD", "test-password")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db_session
from app.core.database import Base
from app.main import app


@pytest.fixture()
def db_session():
    # StaticPool: una sola conexión compartida, necesaria para que las tablas
    # creadas por create_all() sean visibles en la misma base sqlite in-memory
    # (cada conexión nueva a ":memory:" es, si no, una base vacía distinta).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.automation import models as _automation_models  # noqa: F401
    from app.memory import models as _memory_models  # noqa: F401
    from app.notifications import models as _notifications_models  # noqa: F401
    from app.personality import models as _personality_models  # noqa: F401
    from app.security import audit as _audit_models  # noqa: F401
    from app.smart_home import models as _smart_home_models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    """Loguea con la contraseña de test y devuelve el header Authorization
    listo para usar — ejercita el flujo de login real en vez de mockearlo."""
    response = client.post("/api/v1/auth/login", json={"password": "test-password"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
