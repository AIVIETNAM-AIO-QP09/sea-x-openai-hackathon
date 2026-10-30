"""M1 gate on ``mock-data/out/demo`` (12 · M1): 6 history files in < 60 s, SKU
matching ≥ 90 % automatic with ≤ 1 % wrong, ``hourly_panel`` 300 SKU × 2.880 h,
no PII. The full scoring report is ``python -m eval.eval_data --size demo``."""

from __future__ import annotations

import time
from pathlib import Path

import duckdb
import pytest

from app.warehouse import repo
from eval.eval_data import scan_pii, score_matching
from tests.mockdata import load_mock, require

pytestmark = pytest.mark.e2e


def test_demo_ingest_meets_m1(tmp_path: Path) -> None:
    require("demo")
    conn = duckdb.connect(str(tmp_path / "demo.duckdb"))
    t0 = time.perf_counter()
    report, _ = load_mock(conn, "demo", build_panel=True)
    seconds = time.perf_counter() - t0
    assert all(f.status == "loaded" for f in report.files)
    assert seconds < 60, seconds
    shape = conn.execute(
        "SELECT count(*), count(DISTINCT sku_id), count(DISTINCT hour_utc) FROM hourly_panel"
    ).fetchone()
    assert shape == (300 * 2880, 300, 2880)
    hard = score_matching(conn, "demo")["inventory+cost"]
    assert hard["auto_rate"] >= 0.90 and hard["wrong_rate"] <= 0.01
    assert scan_pii(conn)["hits"] == 0
    assert repo.count_rows(conn, "orders") > 100_000
    conn.close()
