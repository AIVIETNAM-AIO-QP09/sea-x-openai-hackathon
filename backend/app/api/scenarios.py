"""Scenarios, break-even and recommendations (API-05, 08 §3.8–3.9, 05 §1).

``POST /scenarios/run`` wraps :func:`app.simulator.service.run_simulation`:

* body = ``SimRequest`` (+ optional ``goal_id`` → active goal of the campaign, and
  ``disable_skus`` for the what-if "tắt riêng SKU": 409 ``CONSTRAINT_VIOLATION`` on a shared
  budget, 05 §5.4).
* ``param_overrides`` apply to this run only; unknown key / out of range → 400
  ``PARAM_OUT_OF_RANGE``; ``restock_delay_days`` accepts −7..7 (negative = arrives early).
* ``samples``: the web sends 300 while a slider is dragged and 1000 on release.
* Missing cost / price → 422 ``BLOCKING_DATA_ISSUE`` (details carry the reasons).
* Response ``ScenarioRun``: the request as run (start / horizon resolved), every action's
  ``ScenarioResult`` (``spend``, ``units_sold``, ``leftover_units`` for every action), the
  ``Recommendation`` with ``reason_sources`` and ``zone_bar.inputs``; ``meta.cache_hit``.

Runs are serialised by one lock: the first run at a new start computes the forecasts
(~10–25 s); later runs read them from ``forecasts`` (< 1 s).
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Annotated, Any, Literal

import duckdb
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.api.common import MAX_LIMIT, compute_state, data_as_of, paginate, parse_json
from app.api.deps import Conn, Operator, Viewer, audit, publish
from app.api.schemas import Envelope, LocalDatetime, Meta, Page, SourceRef
from app.core.errors import DataQualityError, NotFound, ParamOutOfRange, ValidationFailed
from app.core.events import RecommendationChanged
from app.core.timeutil import to_utc, utcnow
from app.economics.breakeven import BreakevenRequest, ZoneBar, uniform_breakeven
from app.economics.goals import active_goal
from app.simulator.constraints import check_sku_toggle
from app.simulator.schemas import (
    ActionSpec,
    Dist,
    FlipCondition,
    InputsRef,
    Recommendation,
    ScenarioResult,
    SimOutput,
    SimRequest,
    SkuOutcome,
)
from app.simulator.service import run_simulation
from app.warehouse.repo import fetch_all, fetch_one

router = APIRouter(tags=["scenarios"])

_RUN_LOCK = threading.Lock()
_RUNS: OrderedDict[str, ScenarioRun] = OrderedDict()
_RUNS_MAX = 64


# ---------------------------------------------------------------------- models
class ScenarioRunRequest(SimRequest):
    """``SimRequest`` of 05 §1 with two API additions (both optional)."""

    goal_id: str | None = None  # type: ignore[assignment]  # None → active goal of campaign
    disable_skus: list[str] | None = Field(
        default=None, description="What-if 'tắt riêng SKU' (chỉ hợp lệ khi chiến dịch 1 SKU)"
    )


class SimRequestOut(SimRequest):
    """The request as run (start / horizon resolved); times with ``+07:00``."""

    start: LocalDatetime | None = None


class SkuOutcomeOut(SkuOutcome):
    stockout_hour_p50: LocalDatetime | None


class ScenarioResultOut(ScenarioResult):
    key: str  # ActionSpec.key, e.g. "schedule_hours:0-2,12-14"
    label: str  # Vietnamese label of the action
    stockout_hour_p50: LocalDatetime | None
    per_sku: list[SkuOutcomeOut]  # type: ignore[assignment]
    lost_units: Dist | None = None  # type: ignore[assignment]  # not stored in DB


class InputsRefOut(InputsRef):
    data_as_of: LocalDatetime | None


class RecommendationOut(Recommendation):
    inputs_ref: InputsRefOut
    created_at: LocalDatetime | None = None
    best_label: str | None = None
    runner_up_label: str | None = None
    reason_sources: list[SourceRef | None] = Field(default_factory=list)
    active: bool = True


class ScenarioRun(BaseModel):
    scenario_id: str
    request: SimRequestOut
    results: list[ScenarioResultOut]
    recommendation: RecommendationOut | None
    cache_hit: bool = False
    input_hash: str | None = None
    blocked: bool = False
    timings_ms: dict[str, float] = Field(default_factory=dict)
    requested_by: str | None = None
    created_at: LocalDatetime | None = None


# ---------------------------------------------------------------------- mapping
def _forecast_skus(conn: duckdb.DuckDBPyConnection, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = conn.execute(
        "SELECT sku_id, forecast_id FROM forecasts WHERE list_contains(?, forecast_id)", [ids]
    ).fetchall()
    return {str(r[0]): str(r[1]) for r in rows}


def reason_sources(conn: duckdb.DuckDBPyConnection, rec: Recommendation) -> list[SourceRef | None]:
    """One source per reason, same order (M3-web §6). Matched on the wording produced by
    ``simulator.recommend``; anything else points to the scenario run itself."""
    ref = rec.inputs_ref
    fc = _forecast_skus(conn, ref.forecast_ids)
    cid = rec.campaign_id
    out: list[SourceRef | None] = []
    for text in rec.reasons:
        low = text.lower()
        sku = next((s for s in sorted(fc, key=len, reverse=True) if s in text), None)
        src: SourceRef
        if "cam kết" in low:
            src = SourceRef(
                id=f"commit-{cid}",
                kind="commitment",
                label=f"Cam kết chương trình sale của {cid}",
                tool="get_campaign_status",
                href=f"/api/v1/campaigns/{cid}",
            )
        elif sku and ("hết" in low or "nhu cầu" in low):
            src = SourceRef(
                id=fc[sku],
                kind="forecast",
                label=f"Dự báo nhu cầu {sku}",
                tool="get_forecast",
                href=f"/api/v1/skus/{sku}/forecast",
            )
        elif "dự báo" in low and fc:
            first = sorted(fc)[0]
            src = SourceRef(
                id=fc[first],
                kind="forecast",
                label="Dự báo nhu cầu",
                tool="get_forecast",
                href=f"/api/v1/skus/{first}/forecast",
            )
        elif sku and " lãi " in f" {low} ":
            src = SourceRef(
                id=f"m-{sku}",
                kind="contribution",
                label=f"Giá bán, giá vốn, phí sàn của {sku}",
                tool="get_sku_snapshot",
                href=f"/api/v1/skus/{sku}",
            )
        elif ("ads" in low or "iroas" in low) and ref.estimate_id:
            src = SourceRef(
                id=ref.estimate_id,
                kind="iroas",
                label=f"Ước lượng iROAS {cid}",
                tool="get_iroas",
                href=f"/api/v1/campaigns/{cid}/iroas",
            )
        elif rec.scenario_id:
            src = SourceRef(
                id=rec.scenario_id,
                kind="scenario",
                label="Kết quả mô phỏng các lựa chọn",
                tool="run_scenario",
                href=f"/api/v1/scenarios/{rec.scenario_id}",
            )
        else:
            out.append(None)
            continue
        src.data_as_of = ref.data_as_of
        out.append(src)
    return out


def rec_out(
    conn: duckdb.DuckDBPyConnection, rec: Recommendation, *, active: bool = True
) -> RecommendationOut:
    d = rec.model_dump()
    return RecommendationOut(
        **d,
        best_label=rec.best.label_vi() if rec.best else None,
        runner_up_label=rec.runner_up.label_vi() if rec.runner_up else None,
        reason_sources=reason_sources(conn, rec),
        active=active and rec.superseded_by is None,
    )


def result_out(r: ScenarioResult) -> ScenarioResultOut:
    return ScenarioResultOut(**r.model_dump(), key=r.action.key, label=r.action.label_vi())


def run_meta(conn: duckdb.DuckDBPyConnection, run: ScenarioRun) -> Meta:
    rec = run.recommendation
    ref = rec.inputs_ref if rec else None
    sources: list[SourceRef] = [
        SourceRef(
            id=run.scenario_id,
            kind="scenario",
            label="Mô phỏng các lựa chọn",
            data_as_of=ref.data_as_of if ref else None,
            tool="run_scenario",
            href=f"/api/v1/scenarios/{run.scenario_id}",
        )
    ]
    if ref is not None:
        fc = _forecast_skus(conn, ref.forecast_ids)
        sources += [
            SourceRef(
                id=fid,
                kind="forecast",
                label=f"Dự báo {sku}",
                data_as_of=ref.data_as_of,
                tool="get_forecast",
                href=f"/api/v1/skus/{sku}/forecast",
            )
            for sku, fid in sorted(fc.items())
        ]
        if ref.estimate_id:
            sources.append(
                SourceRef(
                    id=ref.estimate_id,
                    kind="iroas",
                    label=f"Ước lượng iROAS {rec.campaign_id}" if rec else "iROAS",
                    tool="get_iroas",
                    href=f"/api/v1/campaigns/{rec.campaign_id}/iroas" if rec else None,
                )
            )
    return Meta(
        data_as_of=ref.data_as_of if ref else None,
        computed_at=(rec.created_at if rec and rec.created_at else run.created_at) or utcnow(),
        compute_state=compute_state(ref.data_as_of if ref else None, data_as_of(conn)),
        confidence=rec.confidence if rec else None,
        sources=sources,
        cache_hit=run.cache_hit,
    )


def _remember(run: ScenarioRun) -> None:
    _RUNS[run.scenario_id] = run
    _RUNS.move_to_end(run.scenario_id)
    while len(_RUNS) > _RUNS_MAX:
        _RUNS.popitem(last=False)


# ---------------------------------------------------------------------- DB read-back
def rec_from_row(r: dict[str, Any], inputs_ref: Any) -> Recommendation:
    ref = parse_json(inputs_ref) or {}
    zb = parse_json(r["zone_bar"])
    return Recommendation(
        recommendation_id=r["recommendation_id"],
        campaign_id=r["campaign_id"],
        status=r["status"],
        best=ActionSpec.model_validate(parse_json(r["best_action"])) if r["best_action"] else None,
        runner_up=ActionSpec.model_validate(parse_json(r["runner_up"])) if r["runner_up"] else None,
        p_best_beats_runner_up=r["p_best"],
        expected_gain_vnd=r["expected_gain_vnd"],
        zone_bar=ZoneBar.model_validate(zb) if zb else None,
        flip_conditions=[
            FlipCondition.model_validate(f) for f in parse_json(r["flip_conditions"]) or []
        ],
        confidence=r["confidence"],
        reasons=list(r["reasons"] or []),
        inputs_ref=InputsRef.model_validate(
            {
                "forecast_ids": ref.get("forecast_ids", []),
                "estimate_id": ref.get("estimate_id"),
                "param_version": ref.get("param_version", {}),
                "goal_id": ref.get("goal_id", ""),
                "data_as_of": ref.get("data_as_of"),
                "panel_version": ref.get("panel_version"),
                "iroas_source": ref.get("iroas_source", "prior"),
            }
        ),
        scenario_id=r["scenario_id"],
        created_at=r["created_at"],
        superseded_by=r["superseded_by"],
    )


_REC_SQL = (
    "SELECT r.recommendation_id, r.scenario_id, r.campaign_id, r.status, r.best_action,"
    " r.runner_up, r.p_best, r.expected_gain_vnd, r.zone_bar, r.flip_conditions, r.confidence,"
    " r.reasons, r.superseded_by, r.created_at, s.inputs_ref, s.goal_id"
    " FROM recommendations r LEFT JOIN scenarios s USING (scenario_id)"
)


def load_run(conn: duckdb.DuckDBPyConnection, scenario_id: str) -> ScenarioRun:
    s = fetch_one(conn, "SELECT * FROM scenarios WHERE scenario_id = ?", [scenario_id])
    if s is None:
        raise NotFound(f"Không có kịch bản {scenario_id}.", scenario_id=scenario_id)
    results: list[ScenarioResultOut] = []
    for r in fetch_all(conn, "SELECT * FROM scenario_results WHERE scenario_id = ?", [scenario_id]):
        action = ActionSpec.model_validate(parse_json(r["action"]))
        results.append(
            ScenarioResultOut(
                action=action,
                key=action.key,
                label=action.label_vi(),
                feasible=bool(r["feasible"]),
                violations=list(r["violations"] or []),
                objective=Dist.model_validate(parse_json(r["objective"])),
                contribution=Dist.model_validate(parse_json(r["contribution"])),
                spend=Dist.model_validate(parse_json(r["spend"])),
                units_sold=Dist.model_validate(parse_json(r["units_sold"])),
                leftover_units=Dist.model_validate(parse_json(r["leftover_units"])),
                leftover_value=Dist.model_validate(parse_json(r["leftover_value"])),
                lost_units=None,
                stockout_hour_p50=r["stockout_hour_p50"],
                per_sku=[SkuOutcomeOut.model_validate(x) for x in parse_json(r["per_sku"]) or []],
            )
        )
    order = {"continue": 0, "pause": 1, "reduce_budget": 2, "schedule_hours": 3}
    results.sort(key=lambda x: (order.get(x.action.kind, 9), x.key))
    rr = fetch_one(conn, _REC_SQL + " WHERE r.scenario_id = ?", [scenario_id])
    rec = rec_out(conn, rec_from_row(rr, rr["inputs_ref"])) if rr else None
    overrides = parse_json(s["overrides"]) or {}
    req = SimRequestOut(
        campaign_id=s["campaign_id"],
        start=s["start_at"],
        horizon_hours=s["horizon_hours"],
        goal_id=s["goal_id"],
        actions=[x.action for x in results] or None,
        param_overrides=overrides,
        samples=s["samples"],
        seed=s["seed"],
    )
    return ScenarioRun(
        scenario_id=scenario_id,
        request=req,
        results=results,
        recommendation=rec,
        input_hash=s["input_hash"],
        requested_by=s["requested_by"],
        created_at=s["created_at"],
    )


# ---------------------------------------------------------------------- endpoints
def _resolve_goal(conn: duckdb.DuckDBPyConnection, body: ScenarioRunRequest) -> str:
    if body.goal_id:
        return body.goal_id
    g = active_goal(conn, body.campaign_id)
    if g is None:
        raise DataQualityError(
            f"Chiến dịch {body.campaign_id} chưa có mục tiêu. Lead cần đặt mục tiêu trước"
            " (POST /goals).",
            campaign_id=body.campaign_id,
            missing="goal",
        )
    return g.goal_id


def _check_leftover(conn: duckdb.DuckDBPyConnection, body: ScenarioRunRequest) -> None:
    """``leftover_value_per_unit`` has no fixed max (05 §3: ≤ selling price). The simulator
    bounds only ``key@SKU`` overrides, so the API bounds the plain key by the highest
    selling price of the campaign's SKUs."""
    for raw, v in body.param_overrides.items():
        key, _, sku = raw.partition("@")
        if key != "leftover_value_per_unit" or not isinstance(v, int | float):
            continue
        row = conn.execute(
            "SELECT max(coalesce(s.list_price, 0)) FROM skus s"
            + (
                " WHERE s.sku_id = ?"
                if sku
                else " JOIN campaign_skus cs USING (sku_id) WHERE cs.campaign_id = ?"
                " AND NOT s.is_bundle"
            ),
            [sku or body.campaign_id],
        ).fetchone()
        price = float(row[0]) if row and row[0] else None
        if price is not None and float(v) > price:
            raise ParamOutOfRange(
                f"Giá trị hàng dư {v:,.0f}đ lớn hơn giá bán {price:,.0f}đ.".replace(",", "."),
                key=raw,
                min=0,
                max=price,
                got=v,
            )


def _check_toggle(conn: duckdb.DuckDBPyConnection, body: ScenarioRunRequest) -> None:
    if not body.disable_skus:
        return
    row = conn.execute(
        "SELECT sku_level_control FROM campaigns WHERE campaign_id = ?", [body.campaign_id]
    ).fetchone()
    skus = [
        str(r[0])
        for r in conn.execute(
            "SELECT sku_id FROM campaign_skus WHERE campaign_id = ? ORDER BY 1", [body.campaign_id]
        ).fetchall()
    ]
    if row is None:
        raise NotFound(f"Không có chiến dịch {body.campaign_id}.", campaign_id=body.campaign_id)
    unknown = [s for s in body.disable_skus if s not in skus]
    if unknown:
        raise ValidationFailed(
            f"SKU không thuộc chiến dịch {body.campaign_id}: {', '.join(unknown)}.",
            skus=unknown,
        )
    check_sku_toggle(body.campaign_id, bool(row[0]), skus)  # 409 on a shared budget
    raise ValidationFailed(
        "Chiến dịch chỉ có 1 SKU: tắt SKU này chính là hành động 'Tạm dừng'.",
        hint={"actions": [{"kind": "pause"}]},
    )


@router.post("/scenarios/run", response_model=Envelope[ScenarioRun], summary="Chạy mô phỏng")
def run_scenario(
    body: ScenarioRunRequest, conn: Conn, user: Operator, request: Request
) -> Envelope[ScenarioRun]:
    t0 = time.perf_counter()
    if (
        conn.execute("SELECT 1 FROM campaigns WHERE campaign_id = ?", [body.campaign_id]).fetchone()
        is None
    ):
        raise NotFound(f"Không có chiến dịch {body.campaign_id}.", campaign_id=body.campaign_id)
    _check_toggle(conn, body)
    _check_leftover(conn, body)
    goal_id = _resolve_goal(conn, body)
    req = SimRequest.model_validate(
        {
            **body.model_dump(exclude={"disable_skus"}),
            "goal_id": goal_id,
            # UTC so that the simulator cache key does not depend on the client's offset
            "start": to_utc(body.start) if body.start else None,
        }
    )
    events: list[RecommendationChanged] = []
    with _RUN_LOCK:
        out: SimOutput = run_simulation(conn, req, requested_by="user", events=events)
    rec = out.recommendation
    if out.blocked:
        raise DataQualityError(
            rec.reasons[0] if rec.reasons else None,
            reasons=rec.reasons,
            campaign_id=req.campaign_id,
            recommendation=rec.model_dump(mode="json"),
        )
    srow = conn.execute(
        "SELECT start_at, horizon_hours, created_at FROM scenarios WHERE scenario_id = ?",
        [out.scenario_id],
    ).fetchone()
    ran = SimRequestOut.model_validate(
        {**req.model_dump(), **({"start": srow[0], "horizon_hours": srow[1]} if srow else {})}
    )
    run = ScenarioRun(
        scenario_id=out.scenario_id,
        request=ran,
        results=[result_out(r) for r in out.results],
        recommendation=rec_out(conn, rec),
        cache_hit=out.cache_hit,
        input_hash=out.input_hash,
        blocked=out.blocked,
        timings_ms={**out.timings_ms, "api_total": (time.perf_counter() - t0) * 1e3},
        requested_by="user",
        created_at=srow[2] if srow else utcnow(),
    )
    if not out.cache_hit:
        _remember(run)
        audit(
            conn,
            request,
            user,
            "scenario.run",
            "campaign",
            req.campaign_id,
            after={"scenario_id": out.scenario_id, "samples": req.samples},
        )
    publish(request, *events)
    return Envelope[ScenarioRun](data=run, meta=run_meta(conn, run))


@router.get(
    "/scenarios/{scenario_id}", response_model=Envelope[ScenarioRun], summary="Một kịch bản"
)
def get_scenario(scenario_id: str, conn: Conn, _user: Viewer) -> Envelope[ScenarioRun]:
    run = _RUNS.get(scenario_id) or load_run(conn, scenario_id)
    if run.recommendation is not None:
        row = conn.execute(
            "SELECT superseded_by FROM recommendations WHERE recommendation_id = ?",
            [run.recommendation.recommendation_id],
        ).fetchone()
        sup = row[0] if row else None
        run = run.model_copy(
            update={
                "cache_hit": False,
                "recommendation": run.recommendation.model_copy(
                    update={"superseded_by": sup, "active": sup is None}
                ),
            }
        )
    return Envelope[ScenarioRun](data=run, meta=run_meta(conn, run))


class BreakevenOut(BaseModel):
    zone_bar: ZoneBar | None
    flip_leftover_value_vnd: int | None
    pi_continue_vnd: int
    status: str  # ok | hold_better | pause_sure | continue_sure
    q_star_units: float | None
    reason: str | None


@router.post(
    "/scenarios/breakeven", response_model=Envelope[BreakevenOut], summary="Ngưỡng hòa vốn"
)
def breakeven(body: BreakevenRequest, _user: Operator) -> Envelope[BreakevenOut]:
    lo, mid, hi = body.pause_rate_interval
    if not 0 <= lo <= mid <= hi:
        raise ValidationFailed(
            "pause_rate_interval phải là [p10, p50, p90] tăng dần, không âm.",
            got=list(body.pause_rate_interval),
        )
    res = uniform_breakeven(body.case())
    bar = res.zone_bar
    if bar is not None:
        bar = bar.model_copy(update={"inputs": body})
    reason = None
    if res.point.status == "hold_better":
        reason = "Giữ hàng lợi hơn bán: giá trị hàng dư ≥ đóng góp mỗi sp, không có ngưỡng"
    return Envelope[BreakevenOut](
        data=BreakevenOut(
            zone_bar=bar,
            flip_leftover_value_vnd=(
                round(res.flip_leftover_value_vnd)
                if res.flip_leftover_value_vnd is not None
                else None
            ),
            pi_continue_vnd=round(res.pi_continue),
            status=res.point.status,
            q_star_units=res.point.q_star,
            reason=reason,
        ),
        meta=Meta(computed_at=utcnow(), compute_state="fresh", confidence="scenario"),
    )


@router.get("/recommendations", response_model=Page[RecommendationOut], summary="Đề xuất hiện hành")
def list_recommendations(
    conn: Conn,
    _user: Viewer,
    campaign_id: str | None = None,
    sku: str | None = None,
    active: bool = True,
    status: Literal["recommend", "undetermined", "none_meets_goal"] | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
    cursor: str | None = None,
) -> Page[RecommendationOut]:
    cond: list[str] = ["TRUE"]
    params: list[Any] = []
    if campaign_id:
        cond.append("r.campaign_id = ?")
        params.append(campaign_id)
    if sku:
        cond.append("r.campaign_id IN (SELECT campaign_id FROM campaign_skus WHERE sku_id = ?)")
        params.append(sku)
    if active:
        cond.append("r.superseded_by IS NULL")
    if status:
        cond.append("r.status = ?")
        params.append(status)
    rows = fetch_all(
        conn, _REC_SQL + f" WHERE {' AND '.join(cond)} ORDER BY r.created_at DESC", params
    )
    page, nxt = paginate(rows, limit, cursor)
    items = [rec_out(conn, rec_from_row(r, r["inputs_ref"])) for r in page]
    as_of = data_as_of(conn)
    newest = max((i.inputs_ref.data_as_of for i in items if i.inputs_ref.data_as_of), default=None)
    return Page[RecommendationOut](
        data=items,
        meta=Meta(
            data_as_of=as_of,
            computed_at=max((i.created_at for i in items if i.created_at), default=None),
            compute_state=compute_state(newest, as_of) if items else None,
        ),
        next_cursor=nxt,
    )


@router.get(
    "/recommendations/{recommendation_id}",
    response_model=Envelope[RecommendationOut],
    summary="Một đề xuất",
)
def get_recommendation(
    recommendation_id: str, conn: Conn, _user: Viewer
) -> Envelope[RecommendationOut]:
    r = fetch_one(conn, _REC_SQL + " WHERE r.recommendation_id = ?", [recommendation_id])
    if r is None:
        raise NotFound(f"Không có đề xuất {recommendation_id}.", id=recommendation_id)
    rec = rec_out(conn, rec_from_row(r, r["inputs_ref"]))
    ref = rec.inputs_ref
    return Envelope[RecommendationOut](
        data=rec,
        meta=Meta(
            data_as_of=ref.data_as_of,
            computed_at=rec.created_at,
            compute_state=compute_state(ref.data_as_of, data_as_of(conn)),
            confidence=rec.confidence,
            sources=[s for s in rec.reason_sources if s is not None],
        ),
    )
