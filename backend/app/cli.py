"""Command line: ``uv run python -m app.cli <command>`` (01 §5, INF-04).

Implemented: ``migrate``, ``reset``, ``seed``, ``serve``, ``tables``.
Stubs (exit code 3, message names the owning task): ``ingest``, ``rebuild-panel``,
``backtest``, ``fit``, ``estimate-ads``, ``eval``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from app.core import messages_vi as vi
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.warehouse import repo
from app.warehouse.db import Database, get_db, set_db

EXIT_NOT_IMPLEMENTED = 3

cli = typer.Typer(
    name="megaday",
    help="MegaDay Twin backend CLI.",
    no_args_is_help=True,
    add_completion=False,
)

DbOpt = Annotated[
    Path | None,
    typer.Option("--db", help="Đường dẫn DuckDB (mặc định DUCKDB_PATH trong .env)."),
]


def _db(path: Path | None) -> Database:
    if path is not None:
        set_db(Database(path))
    return get_db()


@cli.callback()
def _main(
    log_level: Annotated[str | None, typer.Option(help="Ghi đè LOG_LEVEL.")] = None,
) -> None:
    s = get_settings()
    configure_logging(log_level or s.log_level, json=s.log_json)


# ------------------------------------------------------------------ implemented
@cli.command()
def migrate(
    db: DbOpt = None,
    seed: Annotated[bool, typer.Option(help="Nạp khai báo mẫu (combo) sau khi migrate.")] = True,
) -> None:
    """Tạo/cập nhật mọi bảng DuckDB (idempotent)."""
    database = _db(db)
    tables = database.migrate()
    typer.echo(vi.CLI_MIGRATE_DONE.format(path=database.path, n_tables=len(tables)))
    if seed:
        n = repo.seed_bundles(database.write)
        typer.echo(vi.CLI_SEED_DONE.format(n=n))
    database.close()


@cli.command()
def reset(
    db: DbOpt = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Không hỏi lại.")] = False,
    seed: Annotated[bool, typer.Option(help="Nạp khai báo mẫu sau khi tạo lại.")] = True,
) -> None:
    """Xóa file DuckDB rồi migrate lại từ đầu."""
    database = _db(db)
    if not yes and not typer.confirm(vi.CLI_RESET_CONFIRM.format(path=database.path)):
        typer.echo(vi.CLI_RESET_ABORTED)
        raise typer.Exit(1)
    database.reset()
    typer.echo(vi.CLI_RESET_DONE.format(path=database.path))
    if seed:
        typer.echo(vi.CLI_SEED_DONE.format(n=repo.seed_bundles(database.write)))
    database.close()


@cli.command()
def seed(db: DbOpt = None) -> None:
    """Nạp khai báo onboarding mẫu (combo COMBO-NOICHIEN, WH-02)."""
    database = _db(db)
    database.migrate()
    typer.echo(vi.CLI_SEED_DONE.format(n=repo.seed_bundles(database.write)))
    database.close()


@cli.command()
def tables(db: DbOpt = None) -> None:
    """Liệt kê bảng và số dòng."""
    database = _db(db)
    conn = database.write
    for name in database.migrate():
        typer.echo(f"{name:24s} {repo.count_rows(conn, name):>10d}")
    database.close()


@cli.command()
def serve(
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8000,
    reload: Annotated[bool, typer.Option(help="Tự nạp lại khi sửa code.")] = False,
) -> None:
    """Chạy API (uvicorn app.main:app)."""
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


# ------------------------------------------------------------------ stubs
def _todo(command: str, task: str, plan: str) -> NoReturn:
    typer.echo(vi.CLI_NOT_IMPLEMENTED.format(command=command, task=task, plan=plan), err=True)
    raise typer.Exit(EXIT_NOT_IMPLEMENTED)


@cli.command()
def ingest(
    dir: Annotated[Path, typer.Option("--dir", help="Thư mục chứa file của shop.")] = Path(
        "../mock-data/out/demo"
    ),
) -> None:
    """Nạp file lịch sử (adapter → kiểm lỗi → ghép SKU → warehouse → panel)."""
    _todo("ingest", "ING-01..ING-08, PNL-01", "docs/dev-plan/02-lop-du-lieu.md §1")


@cli.command("rebuild-panel")
def rebuild_panel() -> None:
    """Dựng lại toàn bộ hourly_panel."""
    _todo("rebuild-panel", "PNL-01..PNL-04", "docs/dev-plan/02-lop-du-lieu.md §6")


@cli.command()
def backtest() -> None:
    """Chạy backtest 6 mốc, ghi model_scores, chọn champion."""
    _todo("backtest", "FC-09", "docs/dev-plan/03-lop-mo-hinh.md §7")


@cli.command()
def fit() -> None:
    """Fit lô dự báo cho mọi SKU (job hằng đêm)."""
    _todo("fit", "FC-09, ORC-03", "docs/dev-plan/06-dieu-phoi-va-hieu-nang.md §3")


@cli.command("estimate-ads")
def estimate_ads() -> None:
    """Ước lượng iROAS cho mọi chiến dịch."""
    _todo("estimate-ads", "ADS-06", "docs/dev-plan/04-hieu-qua-ads.md §7")


@cli.command("eval")
def eval_(
    dir: Annotated[Path, typer.Option("--dir")] = Path("../mock-data/out/demo"),
) -> None:
    """Chấm điểm bằng đáp án (chạy backend/eval, không nằm trong app/)."""
    _todo("eval", "EVAL-02", "docs/dev-plan/11-kiem-thu-va-cham-diem.md §2")


def _utf8_console() -> None:
    """Windows consoles/pipes default to cp1252; Vietnamese output needs UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    _utf8_console()
    cli()


if __name__ == "__main__":
    main()
