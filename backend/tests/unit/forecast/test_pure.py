"""Pure functions: censoring, metrics, labels, CUSUM, champion selection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.core.events import DriftDetected
from app.forecast import censoring
from app.forecast.drift import active_up, cusum, scan
from app.forecast.labels import confidence_label, decide_label
from app.forecast.metrics import ScoreRow, aggregate, bias, coverage, pinball, wape
from app.forecast.registry import select_champions


# ---------------------------------------------------------------------- censoring
def _flat(days: int, rate: float) -> tuple[np.ndarray, np.ndarray]:
    prof = np.full(24, 1 / 24)
    y = np.full((1, days, 24), rate / 24)
    exp = np.broadcast_to(prof, (1, days, 24)).copy()
    return y, exp


def test_censoring_recovers_level_and_demand() -> None:
    y, exp = _flat(20, 24.0)  # 1 unit / hour
    so = np.zeros_like(y, dtype=bool)
    so[0, 15:, 12:] = True  # afternoon stockouts on the last 5 days
    y_obs = np.where(so, 0.0, y)
    pres = np.ones_like(so)
    conf = np.ones_like(y)
    c = censoring.adjust_demand(y_obs, pres, so, conf, exp)
    raw = censoring.adjust_demand(y_obs, pres, so, conf, exp, censoring=False)
    assert np.allclose(c.level[0, -1], 24.0)
    assert np.allclose(c.demand_adj[0, 15:], 24.0)
    assert np.allclose(raw.demand_adj[0, 15:], 12.0)
    assert c.stockout_hours[0, -1] == 12


def test_censoring_keeps_last_units_of_a_stockout_hour() -> None:
    y, exp = _flat(3, 24.0)
    so = np.zeros_like(y, dtype=bool)
    so[0, 2, 10] = True
    y[0, 2, 10] = 5.0  # sold the last 5 units in the hour the shelf emptied
    c = censoring.adjust_demand(y, np.ones_like(so), so, np.ones_like(y), exp)
    assert c.demand_adj[0, 2] == pytest.approx(23 + 5)


def test_low_confidence_hours_count_half() -> None:
    w = censoring.level_weights(np.array([True, True, False]), np.array([1.0, 0.5, 1.0]))
    assert w.tolist() == [1.0, 0.5, 0.0]


# ---------------------------------------------------------------------- metrics
def test_metrics_basic() -> None:
    y = np.array([10.0, 0.0, 5.0])
    p = np.array([8.0, 1.0, 5.0])
    assert wape(y, p) == pytest.approx(3 / 15)
    assert bias(y, p) == pytest.approx(-1 / 15)
    assert wape(np.zeros(2), np.ones(2)) is None
    assert pinball(np.array([2.0]), np.array([1.0]), 0.9) == pytest.approx(0.9)
    assert pinball(np.array([0.0]), np.array([1.0]), 0.9) == pytest.approx(0.1)
    assert coverage(y, p - 1, p + 1) == pytest.approx(2 / 3)


def test_aggregate_drops_days_without_instock_hours() -> None:
    days = pd.DataFrame(
        {
            "sku_id": ["a", "a", "b"],
            "y": [10.0, 0.0, 4.0],
            "p10": [5.0, 0.0, 2.0],
            "p50": [9.0, 0.0, 4.0],
            "p90": [12.0, 0.0, 6.0],
            "wape_eligible": [True, True, False],
            "pb10": [0.1, 0.0, 0.1],
            "pb50": [0.5, 0.0, 0.2],
            "pb90": [0.1, 0.0, 0.1],
            "n_hours": [24, 0, 24],
        }
    )
    r = aggregate(days, "bt", "on_dinh", "normal", "m")
    assert r.n_sku_days == 2
    assert r.wape == pytest.approx(0.1)  # only the eligible SKU
    assert r.coverage == 1.0


# ---------------------------------------------------------------------- labels
def _score(w: float | None, c: float | None, n: int = 60) -> ScoreRow:
    return ScoreRow("m", "bt", "on_dinh", "normal", 10, n, w, 0.0, 0.1, 0.2, 0.1, c)


def test_confidence_label_rules() -> None:
    assert confidence_label(_score(0.2, 0.8), 30, False) == "verified"
    assert confidence_label(_score(0.2, 0.8), 30, True) == "reference"
    assert confidence_label(_score(0.35, 0.8), 30, False) == "reference"
    assert confidence_label(_score(0.2, 0.95), 30, False) == "reference"
    assert confidence_label(_score(0.2, 0.8, n=20), 30, False) == "reference"
    assert confidence_label(_score(0.1, 0.8), 7, False) == "scenario"
    assert confidence_label(None, 30, False) == "scenario"


def test_decide_label_context_and_nowcast() -> None:
    d = decide_label(None, 60, False, group_scored=True)
    assert d.label == "reference" and "Chưa kiểm ở bối cảnh này" in d.reasons
    assert decide_label(None, 60, False, group_scored=False).label == "scenario"
    assert decide_label(_score(0.2, 0.8), 60, False, group_scored=True, nowcast=True).label == (
        "reference"
    )
    assert decide_label(_score(0.2, 0.8), 5, False, group_scored=True).label == "scenario"


# ---------------------------------------------------------------------- drift
def test_cusum_quiet_then_up() -> None:
    rng = np.random.default_rng(0)
    lam = np.full(48, 2.0)
    y = rng.poisson(lam).astype(float)
    assert not cusum(y, lam, 3.0).alarms
    y2 = y.copy()
    y2[30:] = rng.poisson(8.0, 18)
    tr = cusum(y2, lam, 3.0)
    assert tr.alarms and tr.alarms[0][1] == "up"
    assert 30 <= tr.alarms[0][0] <= 33
    # reset after alarm
    t = tr.alarms[0][0]
    assert tr.s_pos[t] == 0.0


def test_cusum_skips_stockout_hours() -> None:
    lam = np.full(24, 3.0)
    y = np.full(24, 3.0)
    y[8:] = 0.0  # shelf empty from 08:00
    ins = np.ones(24, dtype=bool)
    assert cusum(y, lam, 3.0, ins).alarms[0][1] == "down"
    ins[8:] = False
    assert not cusum(y, lam, 3.0, ins).alarms


def test_scan_events_and_nowcast_window() -> None:
    t0 = datetime(2026, 11, 11, 0, tzinfo=UTC)
    hours = [t0 + timedelta(hours=h) for h in range(10)]
    lam = np.full(10, 1.0)
    y = np.array([1, 1, 6, 7, 8, 9, 9, 9, 9, 9], dtype=float)
    al = scan("X", hours, y, lam, 3.0)
    assert al[0].direction == "up"
    ev = al[0].event()
    assert isinstance(ev, DriftDetected) and ev.sku_id == "X"
    assert "X" in active_up(al, al[0].hour + timedelta(hours=1))
    assert "X" not in active_up(al, al[-1].hour + timedelta(hours=26))


def test_cusum_down_alarm_has_checklist() -> None:
    t0 = datetime(2026, 11, 11, 0, tzinfo=UTC)
    hours = [t0 + timedelta(hours=h) for h in range(12)]
    al = scan("X", hours, np.zeros(12), np.full(12, 4.0), 3.0)
    assert al[0].direction == "down" and al[0].checklist


# ---------------------------------------------------------------------- champions
def _r(model: str, bt: str, w: float, pb: float = 0.2) -> ScoreRow:
    return ScoreRow(model, bt, "on_dinh", "double_day", 10, 60, w, 0.0, 0.1, pb, 0.1, 0.8)


ORDER = {"b1": 0, "b2": 1, "b3": 2}


def test_champion_rule1_tie_uses_pinball() -> None:
    rows = [_r("a", "b1", 0.30, pb=0.30), _r("b", "b1", 0.31, pb=0.20)]
    champs, _ = select_champions(rows, ORDER)
    assert champs[("on_dinh", "double_day")] == "b"
    assert [r.model_id for r in rows if r.is_champion] == ["b"]


def test_challenger_needs_two_consecutive_wins() -> None:
    rows = [
        _r("a", "b1", 0.30),
        _r("b", "b1", 0.40),
        _r("a", "b2", 0.30),
        _r("b", "b2", 0.20),  # first win
        _r("a", "b3", 0.30),
        _r("b", "b3", 0.35),  # loses again → stays a
    ]
    champs, _ = select_champions(rows, ORDER)
    assert champs[("on_dinh", "double_day")] == "a"
    rows2 = [*rows[:4], _r("a", "b3", 0.30), _r("b", "b3", 0.25)]
    champs2, changes2 = select_champions(rows2, ORDER)
    assert champs2[("on_dinh", "double_day")] == "b"
    assert changes2[-1].backtest == "b3" and changes2[-1].old == "a"


def test_incumbent_from_previous_run_kept() -> None:
    rows = [_r("a", "b1", 0.30), _r("b", "b1", 0.25)]
    champs, _ = select_champions(rows, ORDER, {("on_dinh", "double_day"): "a"})
    assert champs[("on_dinh", "double_day")] == "a"
