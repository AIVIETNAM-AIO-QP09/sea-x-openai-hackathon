"""Simulator cache key (05 §5.5): the same instant must give the same key whatever the
offset of ``start`` (M3-whatif: the API converted to UTC itself; fixed at the root)."""

from __future__ import annotations

from app.core.timeutil import to_local
from app.economics.parameters import ParamSet, parse_overrides
from app.simulator.schemas import ActionSpec, SimRequest
from app.simulator.service import _key
from tests.unit.simulator.factory import START, make_inputs, sku

ACTS = [ActionSpec(kind="continue"), ActionSpec(kind="pause")]


def test_cache_key_normalises_start_to_utc() -> None:
    utc = make_inputs([sku("A", 24)], start=START)
    vn = make_inputs([sku("A", 24)], start=to_local(START))
    assert vn.start.utcoffset() != utc.start.utcoffset() and vn.start == utc.start
    req = SimRequest(campaign_id="CDX", goal_id="goal-test")
    assert _key(utc, req, ACTS) == _key(vn, req, ACTS)


def test_cache_key_normalises_override_numbers() -> None:
    a = make_inputs(
        [sku("A", 24)],
        params=ParamSet({}, overrides=parse_overrides({"leftover_value_per_unit": 0})),
    )
    b = make_inputs(
        [sku("A", 24)],
        params=ParamSet({}, overrides=parse_overrides({"leftover_value_per_unit": 0.0})),
    )
    req = SimRequest(campaign_id="CDX", goal_id="goal-test")
    assert _key(a, req, ACTS) == _key(b, req, ACTS)
