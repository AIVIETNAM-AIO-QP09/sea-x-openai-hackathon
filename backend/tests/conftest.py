"""Shared fixtures. Data fixtures for mock-data (``mock_small``, ``loaded_db``,
11 §1) are added by EVAL-01 once ingest exists."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# Never let a developer's backend/.env leak into tests (real key, AI on, …).
os.environ.setdefault("APP_ENV", "test")
os.environ["AI_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = ""
os.environ["LOG_JSON"] = "false"

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.warehouse.db import Database

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, duckdb_path=tmp_path / "test.duckdb", app_env="test")  # type: ignore[call-arg]


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "test.duckdb")
    yield database
    database.close()


@pytest.fixture
def client(settings: Settings, db: Database) -> Iterator[TestClient]:
    app = create_app(settings=settings, db=db)
    with TestClient(app) as c:
        yield c
