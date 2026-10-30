"""SIM-04 / SIM-05 · recommendation rules, zone bar, flip conditions, persistence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import duckdb

from app.economics.parameters import ParamSet, parse_overrides
from app.simulator.engine import Perturb, SimRun, simulate
from app.simulator.recommend import build_recommendation, persist, scenario_results
from app.simulator.schemas import ActionSpec, SimOutput
from app.warehouse.db import migrate
from tests.unit.simulator.factory import make_inputs, sku

ACTS = [
    ActionSpec(kind="continue"),
    ActionSpec(kind="pause"),
    ActionSpec(kind="reduce_budget", pct=0.5),
    ActionSpec(kind="schedule_hours", windows_local=[(0, 2), (12, 14)]),
]


def _run(inp, acts=ACTS, samples=1000):  # type: ignore[no-untyped-def]
    run = simulate(inp, acts, samples, 20261111)

    def resim(a: Sequence[ActionSpec], pt: Perturb, n: int) -> SimRun:
        return simulate(inp, a, n, 20261111, perturb=pt)

    return run, resim


def test_flash_day_schedule_hours_wins() -> None:
    """Toy version of 05 §10: demand ≫ stock, thin margin, committed flash hours."""
    T = 23  # noqa: N806
    noi = sku(
        "NOI",
        T,
        lam=6.0,
        m=9_280,
        price=531_000,
        stock=76,
        reserve=23,
        plans=[(date(2026, 11, 12), 400)],
    )
    inp = make_inputs(
        [noi], T=T, budget=5_592_000, must_run_hours=[0, 1, 12, 13], flash_hours=[0, 1, 12, 13]
    )
    run, resim = _run(inp, [*ACTS, ActionSpec(kind="pause_until_restock")])
    rec, sel = build_recommendation(run, resim)
    assert rec.status == "recommend"
    assert rec.best is not None and rec.best.kind == "schedule_hours"
    assert rec.p_best_beats_runner_up is not None and rec.p_best_beats_runner_up > 0.99
    by = run.by_key()
    assert not by["pause"].feasible and not by["pause_until_restock"].feasible
    assert any("cam kết với sàn" in r for r in rec.reasons)
    assert any("9.280đ" in r for r in rec.reasons)
    res = scenario_results(run, sel)
    assert [r.violations for r in res if r.action.kind == "pause"] == [["campaign_must_run"]]
    assert rec.inputs_ref.forecast_ids == ["fc-NOI"] and rec.inputs_ref.iroas_source == "prior"
    assert "decision_min_prob" in rec.inputs_ref.param_version


def test_undetermined_when_gain_small() -> None:
    inp = make_inputs([sku("A", 24, lam=0.3, m=40_000, stock=1000)], budget=24_000)
    run, resim = _run(inp, ACTS[:2])
    rec, _ = build_recommendation(run, resim, with_flips=False)
    assert rec.status == "undetermined"
    assert rec.best is not None and rec.runner_up is not None


def test_zone_bar_and_flip_on_leftover_value() -> None:
    inp = make_inputs(
        [sku("A", 24, lam=1.5, m=40_000, price=89_000, stock=1000, v=10_000)], budget=600_000
    )
    run, resim = _run(inp, ACTS[:3])
    rec, _ = build_recommendation(run, resim)
    assert rec.zone_bar is not None
    assert rec.zone_bar.verdict in ("pause_better", "undetermined", "continue_better")
    assert [a.label for a in rec.zone_bar.alt_thresholds] == ["hàng dư 0đ"]
    for f in rec.flip_conditions:
        assert f.text.startswith("Nếu")


def test_hold_better_has_no_zone_bar() -> None:
    inp = make_inputs([sku("A", 24, lam=1.0, m=9_000, stock=100, v=200_000)])
    run, resim = _run(inp, ACTS[:2], 300)
    rec, _ = build_recommendation(run, resim, with_flips=False)
    assert rec.zone_bar is None and any("Giữ hàng lợi hơn bán" in r for r in rec.reasons)


def test_sell_target_none_meets_goal() -> None:
    inp = make_inputs([sku("A", 24, lam=1.0, stock=100)], goal_kind="sell_target", target_units=500)
    run, resim = _run(inp, ACTS[:2], 300)
    rec, sel = build_recommendation(run, resim)
    assert rec.status == "none_meets_goal" and rec.best is None
    assert sel.p_target == [0.0, 0.0]
    assert "chưa giải quyết được" in rec.reasons[0]


def test_scenario_param_caps_label() -> None:
    ps = ParamSet(stored={}, overrides=parse_overrides({"rank_loss_after_pause": 0.1}))
    inp = make_inputs([sku("A", 24)], params=ps)
    inp.iroas = inp.iroas.model_copy(update={"confidence": "verified"})
    inp.iroas_source = "estimate"
    for s in inp.skus:
        s.label = "verified"
    run, resim = _run(inp, ACTS[:2], 200)
    rec, _ = build_recommendation(run, resim, with_flips=False)
    assert rec.confidence == "reference"


def test_persist_and_supersede() -> None:
    conn = duckdb.connect()
    migrate(conn)
    inp = make_inputs([sku("A", 24, lam=2.0, stock=100)])
    run, resim = _run(inp, ACTS[:2], 200)
    events = []
    for i in range(2):
        rec, sel = build_recommendation(run, resim, with_flips=False)
        out = SimOutput(
            scenario_id=f"scn-{i}",
            results=scenario_results(run, sel),
            recommendation=rec,
            input_hash="h",
        )
        events.append(
            persist(conn, out, inp, overrides={}, samples=200, seed=1, requested_by="user")
        )
    assert events[0] is not None and events[1] is None  # same best → no change event
    rows = conn.execute(
        "SELECT recommendation_id, superseded_by FROM recommendations ORDER BY created_at"
    ).fetchall()
    assert rows[0][1] == rows[1][0] and rows[1][1] is None
    assert conn.execute("SELECT count(*) FROM scenario_results").fetchone() == (4,)
    sc = conn.execute("SELECT param_version, inputs_ref FROM scenarios").fetchall()
    assert len(sc) == 2 and "forecast_ids" in sc[0][1]
