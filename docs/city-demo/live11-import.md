# Read-only 11.11 demo bootstrap

From `backend/`:

```sh
uv sync
uv run python -m app.demo_import --shop ../mock-data/out/demo --output data/live11-demo-01 --models --serve
```

The launcher calls the existing history ingest (six explicit files) and live-delta pipeline; it does not replace adapters, economic models, API schemas, matching or permissions. History is the training baseline. The sale observations come only from `live_11_11`, filtered into a separate staging directory at the requested `--until` (default 01:00 Vietnam time). Orders/ads are strictly before the cutoff; stock updates may be at the cutoff. Ads fixture timestamps are UTC. Oracle and `_replay.json` are never business inputs. Inputs are opened read-only; staging, cursors, report and DB live in the output directory. Existing output directories are refused rather than reset. `--models` runs the existing backtest, forecast and ads-estimation CLI. `--serve` explicitly injects the isolated Database into FastAPI on localhost:8000, avoiding the normal shared DB. No watcher or hosted Python deployment is implied.

The city Data Studio accepts the six original formats, shop-folder selection or a portable source pack. Its optional server adapter requires DATA_BACKEND_URL (ending /api/v1), DATA_BACKEND_USER and DATA_BACKEND_ROLE. These are explicitly assigned server identity values; signed city login does not grant governance rights. Same-origin source imports use the existing /ingest/files endpoint; campaign execution and schema ownership are unchanged. Held rows/aliases are reviewed through the team API/operations tools. Direct full-day file imports load all observations; use the launcher for a timed checkpoint.

Gateway /api/data-backend is forwarded to CITY_UI. Existing /api/v1 routing, D1 storage, health and the Vite operations workspace are preserved. The hosted city without a Python origin uses a dated 01:00 inventory checkpoint generated through this pipeline and labels it as a checkpoint, never as live inventory. Its imported catalogue is separate from the city sandbox's older three-item decision engine.
