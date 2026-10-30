from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli import EXIT_NOT_IMPLEMENTED, cli
from app.warehouse.db import set_db

runner = CliRunner()


@pytest.fixture(autouse=True)
def _reset_db() -> None:
    yield
    set_db(None)


def test_migrate_and_tables(tmp_path: Path) -> None:
    db = tmp_path / "cli.duckdb"
    r = runner.invoke(cli, ["migrate", "--db", str(db)])
    assert r.exit_code == 0, r.output
    assert "bảng" in r.output
    assert db.exists()
    r = runner.invoke(cli, ["tables", "--db", str(db)])
    assert r.exit_code == 0
    assert "bundle_components" in r.output


def test_reset_yes(tmp_path: Path) -> None:
    db = tmp_path / "cli.duckdb"
    assert runner.invoke(cli, ["migrate", "--db", str(db)]).exit_code == 0
    r = runner.invoke(cli, ["reset", "--db", str(db), "--yes"])
    assert r.exit_code == 0, r.output


@pytest.mark.parametrize(
    ("args", "task"),
    [
        (["ingest", "--dir", "x"], "ING-"),
        (["rebuild-panel"], "PNL-"),
        (["backtest"], "FC-09"),
        (["fit"], "FC-09"),
        (["estimate-ads"], "ADS-06"),
        (["eval"], "EVAL-02"),
    ],
)
def test_stub_commands_report_owner_task(args: list[str], task: str) -> None:
    r = runner.invoke(cli, args)
    assert r.exit_code == EXIT_NOT_IMPLEMENTED
    assert "chưa làm" in r.output
    assert task in r.output
