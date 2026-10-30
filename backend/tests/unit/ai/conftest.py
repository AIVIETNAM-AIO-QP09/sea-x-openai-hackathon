"""Fixtures for the AI layer tests.

* ``mem_conn`` — empty in-memory DuckDB with the schema (registry, logging, stub tools).
* ``ai_settings`` — test settings with the AI on (the client is always a FakeClient).
* ``demo_ai_dbs`` (session, e2e) — the ``demo`` history loaded by the real pipeline, then
  the 11.11 live stream up to 00:59 (file ``0100``) and a copy advanced to 13:59
  (file ``1400``), the two moments of the pitch script (05 §10, 07 §4.3).
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from app.core.config import Settings
from app.warehouse.db import migrate


@pytest.fixture
def mem_conn() -> Iterator[duckdb.DuckDBPyConnection]:
    conn = duckdb.connect(":memory:")
    migrate(conn)
    yield conn
    conn.close()


@pytest.fixture
def ai_settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="test",
        duckdb_path=tmp_path / "ai.duckdb",
        ai_enabled=True,
        ai_mode="live",
        demo_mode=True,
        mc_samples=1000,
    )


@pytest.fixture(scope="session")
def demo_ai_dbs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    from app.ads_effect.iroas import estimate_all, write_estimates
    from app.ingest.pipeline import ingest_live_delta
    from app.panel.build import build_hourly_panel
    from eval.live_replay import write_live_stream
    from tests.mockdata import load_mock, require

    require("demo")
    root = tmp_path_factory.mktemp("ai_demo")
    p1 = root / "demo_0100.duckdb"
    conn = duckdb.connect(str(p1))
    load_mock(conn, "demo", build_panel=False)
    write_live_stream("demo", root / "live_stream", 0)  # orders + stock up to 00:59
    assert ingest_live_delta(conn, root / "live_stream", build_panel=False).status == "loaded"
    build_hourly_panel(conn)
    write_estimates(conn, estimate_all(conn).estimates)
    conn.close()
    p2 = root / "demo_1400.duckdb"
    shutil.copy(p1, p2)
    conn = duckdb.connect(str(p2))
    write_live_stream("demo", root / "live_stream", 13)  # up to 13:59
    assert ingest_live_delta(conn, root / "live_stream", build_panel=True).status == "loaded"
    conn.close()
    return {"0100": p1, "1400": p2}
