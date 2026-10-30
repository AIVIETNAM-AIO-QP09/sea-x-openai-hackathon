from pathlib import Path

from fastapi.testclient import TestClient

from app.demo_import import main
from tests.mockdata import require


def test_demo_launcher_serves_its_isolated_database(tmp_path: Path, monkeypatch) -> None:
    shop = require("nho")
    output = tmp_path / "isolated"
    monkeypatch.setattr(
        "sys.argv", ["demo_import", "--shop", str(shop), "--output", str(output), "--serve"]
    )
    import uvicorn

    def inspect_server(app, **_kwargs):
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/skus?limit=1", headers={"X-User": "test", "X-Role": "viewer"}
            )
            assert response.status_code == 200
            assert len(response.json()["data"]) == 1
            assert app.state.db.path == output / "demo.duckdb"
            assert response.json()["meta"]["data_as_of"].startswith("2026-11-11T01:")

    monkeypatch.setattr(uvicorn, "run", inspect_server)
    main()
    assert (output / "import-report.json").exists()
