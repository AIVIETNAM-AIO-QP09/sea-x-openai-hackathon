"""Recommendation rules, zone bar, sensitivity and persistence (SIM-04, SIM-05; 05 §6–§9).

1. Infeasible actions are dropped (still returned in ``results``).
2. Ranking by the goal (``economics.goals.select_actions``); nothing eligible →
   ``none_meets_goal``.
3. ``best``, ``runner_up``; ``p = mean_s[score_s(best) > score_s(runner_up)]`` on the same
   samples, ``gain = E[J(best)] − E[J(runner_up)]``.
4. ``p ≥ decision_min_prob`` and ``gain ≥ max(decision_min_gain_vnd, 5 %·|E[J(best)]|)`` →
   ``recommend``, else ``undetermined`` (best / runner-up / zone bar / flips still shown).
5. ``confidence`` = min(forecast labels of the SKUs making ≥ 80 % of expected revenue,
   iROAS label, data label); a scenario parameter ≠ 0 caps it at ``reference``.
6. ``reasons``: short Vietnamese sentences with numbers.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import duckdb
import numpy as np
import numpy.typing as npt

from app.core.events import RecommendationChanged
from app.core.ids import new_id
from app.core.money import format_vnd
from app.core.timeutil import to_local, utcnow
from app.economics.breakeven import (
    BreakevenRequest,
    bisect_sign_change,
    linear_root,
    make_zone_bar,
    uniform_breakeven,
)
from app.economics.goals import Outcome, Selection, select_actions
from app.simulator.constraints import MUST_RUN
from app.simulator.engine import ActionRun, Perturb, SimRun, stockout_hour
from app.simulator.inputs import SimInputs
from app.simulator.schemas import (
    ActionSpec,
    Dist,
    FlipCondition,
    InputsRef,
    Label,
    Recommendation,
    ScenarioResult,
    SimOutput,
    SkuOutcome,
    ZoneBar,
    min_label,
)

FloatArr = npt.NDArray[np.float64]
Resim = Callable[[Sequence[ActionSpec], Perturb, int], SimRun]
SENS_SAMPLES = 300
Z90 = 1.2815515655446004


# ---------------------------------------------------------------------- results
def scenario_results(run: SimRun, sel: Selection | None = None) -> list[ScenarioResult]:
    inp = run.inputs
    out = []
    for i, r in enumerate(run.runs):
        per_sku = []
        for s in inp.skus:
            if not s.in_campaign and s.sku_id not in r.sold_by_sku:
                continue
            per_sku.append(
                SkuOutcome(
                    sku_id=s.sku_id,
                    is_bundle=s.is_bundle,
                    contribution_per_unit=float(s.m[0]) if len(s.m) else 0.0,
                    leftover_value_per_unit=s.leftover_value,
                    demand=Dist.of(r.demand_by_sku[s.sku_id]),
                    units_sold=Dist.of(r.sold_by_sku[s.sku_id]),
                    lost_units=Dist.of(r.lost_by_sku[s.sku_id]),
                    leftover_units=(
                        Dist.of(r.leftover_by_sku[s.sku_id]) if not s.is_bundle else None
                    ),
                    stockout_hour_p50=stockout_hour(inp, r.first_lost_t[s.sku_id]),
                )
            )
        main = inp.main_sku
        out.append(
            ScenarioResult(
                action=r.action,
                feasible=r.feasible,
                violations=[c for c, _ in r.violations],
                violation_details=[t for _, t in r.violations],
                objective=Dist.of(r.j),
                contribution=Dist.of(r.contribution),
                spend=Dist.of(r.spend),
                leftover_units=Dist.of(r.leftover_units),
                leftover_value=Dist.of(r.leftover_value),
                units_sold=Dist.of(r.units_sold),
                lost_units=Dist.of(r.lost_units),
                stockout_hour_p50=(
                    stockout_hour(inp, r.first_lost_t[main]) if main in r.first_lost_t else None
                ),
                per_sku=per_sku,
                goal_eligible=sel.eligible[i] if sel is not None else True,
                p_target=sel.p_target[i] if sel is not None else None,
                goal_note=sel.notes.get(i) if sel is not None else None,
            )
        )
    return out


def select(run: SimRun) -> Selection:
    inp = run.inputs
    g = inp.goal
    p = inp.params
    max_loss = float(g.params.get("max_loss_vnd", p.num("max_loss_vnd")))
    return select_actions(
        g.kind,
        [Outcome(r.action.key, r.feasible, r.j, r.units_sold, r.spend) for r in run.runs],
        target_units=g.target_units,
        sell_target_prob=float(g.params.get("sell_target_prob", p.num("sell_target_prob"))),
        max_loss_vnd=max_loss,
        min_marginal_return=float(
            g.params.get("min_marginal_return", p.num("min_marginal_return"))
        ),
    )


# ---------------------------------------------------------------------- confidence
def confidence(inp: SimInputs) -> tuple[Label, list[str]]:
    reasons: list[str] = []
    skus = sorted(
        (s for s in inp.skus if s.in_campaign), key=lambda s: s.revenue_share, reverse=True
    )
    labels: list[str] = []
    cum = 0.0
    for s in skus:
        labels.append(s.label)
        cum += s.revenue_share
        if cum >= 0.8:
            break
    fc = min_label(*labels) if labels else "scenario"
    if fc != "verified":
        reasons.append(f"Dự báo nhu cầu ở mức '{fc}'")
    ads = inp.iroas.confidence
    if inp.iroas_source == "prior":
        reasons.append("Hiệu quả ads đang dùng giả định (chưa có ước lượng iROAS)")
    lab = min_label(fc, ads, inp.data_label)
    if inp.blocked_reasons:
        lab = "scenario"
    active = inp.params.scenario_active()
    if active:
        lab = min_label(lab, "reference")
        reasons.append("Đang dùng giả định: " + ", ".join(active))
    return lab, reasons + inp.data_reasons


# ---------------------------------------------------------------------- zone bar
def zone_bar(run: SimRun, resim: Resim) -> tuple[ZoneBar | None, str | None]:
    """Continue-vs-pause bar from the simulation (05 §7.2)."""
    inp = run.inputs
    by = run.by_key()
    if "continue" not in by or "pause" not in by:
        extra = resim(
            [ActionSpec(kind="continue"), ActionSpec(kind="pause")], Perturb(), run.samples
        )
        by = {**extra.by_key(), **by}
    c, p = by["continue"], by["pause"]
    js = inp.stock_skus
    restock = inp.restock_matrix().sum(axis=1)
    n_j = np.array([s.stock0 for s in js]) + restock
    n = float(n_j.sum())
    if n <= 0 or n >= 1e11:
        return None, None
    v_bar = float(np.dot([s.leftover_value for s in js], n_j) / n)
    sold_c = float(np.mean(c.stock_units_sold))
    m_bar = (
        float(np.mean(c.contribution)) / sold_c
        if sold_c > 0
        else float(np.mean(p.contribution)) / max(float(np.mean(p.stock_units_sold)), 1.0)
    )
    rate = p.stock_units_sold / inp.T
    q = np.quantile(rate, [0.1, 0.5, 0.9])
    pi_c = float(np.mean(c.j))
    alts = []
    if v_bar > 0:
        alts.append((0.0, pi_c - float(np.mean(c.leftover_value))))
    bar, point = make_zone_bar(
        pi_c,
        n,
        inp.T,
        m_bar,
        v_bar,
        (float(q[0]), float(q[1]), float(q[2])),
        spend_p=float(np.mean(p.spend)),
        alt_values=alts,
    )
    if bar is None and point.status == "hold_better":
        return None, (
            f"Giữ hàng lợi hơn bán: mỗi sp còn lại đáng {format_vnd(round(v_bar))},"
            f" bán chỉ lãi {format_vnd(round(m_bar))}"
        )
    if bar is not None:
        bar.inputs = uniform_inputs(
            bar, pi_c, n, float(inp.T), m_bar, v_bar, sold_c, float(np.mean(p.spend))
        )
    return bar, None


def uniform_inputs(
    bar: ZoneBar,
    pi_c: float,
    n: float,
    hours: float,
    m: float,
    v: float,
    sold_c: float,
    spend_p: float,
) -> BreakevenRequest | None:
    """[DEV] Uniform case (body of ``POST /scenarios/breakeven``) equivalent to the simulated
    bar: continue sells ``sold_c`` evenly over ``hours`` and spends ``s``/hour, with ``s``
    chosen so that ``Π_c`` matches the simulation. Exact only when pause spends nothing and
    ``s ≥ 0``; returned only if it reproduces ``bar.threshold`` (else ``None``)."""
    if abs(spend_p) >= 0.5 or hours <= 0 or not 0 <= sold_c <= n:
        return None
    s = (m * sold_c + v * (n - sold_c) - pi_c) / hours
    if s < 0:
        return None
    req = BreakevenRequest(
        units_left=n,
        hours_left=hours,
        contribution_per_unit_vnd=m,
        spend_per_hour_vnd=s,
        rate_continue_per_hour=sold_c / hours,
        pause_rate_interval=bar.interval,
        leftover_value_per_unit_vnd=v,
        alt_leftover_values=[0.0] if v > 0 else [20_000.0],
    )
    check = uniform_breakeven(req.case()).zone_bar
    if check is None or abs(check.threshold - bar.threshold) > 1e-6 * max(1.0, bar.threshold):
        return None
    return req


# ---------------------------------------------------------------------- sensitivity
@dataclass
class _Pair:
    best: ActionSpec
    runner: ActionSpec


def _diff(run: SimRun, pair: _Pair) -> float:
    by = run.by_key()
    return float(np.mean(by[pair.best.key].j - by[pair.runner.key].j))


def flip_conditions(
    run: SimRun, best: ActionRun, runner: ActionRun, resim: Resim
) -> list[FlipCondition]:
    """Value of each factor where ``E[J(best) − J(runner_up)]`` changes sign (05 §8)."""
    inp = run.inputs
    pair = _Pair(best.action, runner.action)
    rb, rr = best.action.label_vi(), runner.action.label_vi()
    out: list[FlipCondition] = []
    base = float(np.mean(best.j - runner.j))
    # who wins (in money) once the factor crosses the flip point
    after = f"{rr if base > 0 else rb} {'tốt hơn' if base > 0 else 'có lợi hơn về tiền'}"

    # 1. leftover value V (enters J linearly → exact root)
    js = [s for s in inp.stock_skus]
    if js:
        dleft = float(np.mean(best.leftover_units - runner.leftover_units))
        dval = float(np.mean(best.leftover_value - runner.leftover_value))
        f0 = base - dval
        root = linear_root(f0, dleft)
        hi = max(float(np.max(s.price)) for s in js)
        v_now = float(np.mean([s.leftover_value for s in js]))
        if root is not None and 0 <= root <= hi and abs(root - v_now) > 1:
            up = root > v_now
            out.append(
                FlipCondition(
                    factor="leftover_value_per_unit",
                    flip_at=round(root),
                    base_value=v_now,
                    unit="đ/sp",
                    text=(
                        f"Nếu hàng dư còn giá trị từ {format_vnd(round(root))}/sp trở "
                        f"{'lên' if up else 'xuống'} → {after}"
                    ),
                )
            )

    def evaluator(make: Callable[[float], Perturb]) -> Callable[[float], float]:
        cache: dict[float, float] = {}

        def f(x: float) -> float:
            if x not in cache:
                cache[x] = _diff(resim([pair.best, pair.runner], make(x), SENS_SAMPLES), pair)
            return cache[x]

        return f

    # 2. demand level within the forecast p10–p90 (main SKU σ)
    main = inp.sku(inp.main_sku) if inp.main_sku else inp.skus[0]
    sig = max(main.sigma, 0.05)
    f_lvl = evaluator(lambda x: Perturb(level=x))
    for end in (float(np.exp(-Z90 * sig)), float(np.exp(Z90 * sig))):
        x = bisect_sign_change(f_lvl, 1.0, end)
        if x is not None and x != 1.0:
            pct = abs(x - 1) * 100
            word = "thấp" if x < 1 else "cao"
            out.append(
                FlipCondition(
                    factor="demand_level",
                    flip_at=round(x, 3),
                    base_value=1.0,
                    unit="hệ số",
                    text=f"Nếu nhu cầu {word} hơn dự báo {pct:.0f}% → {after}",
                )
            )
            break

    # 3. ads effect a within the posterior p10–p90
    a = run.draws.a
    a_mean = float(np.mean(a))
    if a_mean > 0:
        lo, hi_ = (float(v) / a_mean for v in np.quantile(a, [0.1, 0.9]))
        f_ads = evaluator(lambda x: Perturb(ads=x))
        for end in (lo, hi_):
            if abs(end - 1.0) < 1e-6:
                continue
            x = bisect_sign_change(f_ads, 1.0, end)
            if x is not None and x != 1.0:
                word = "kém" if x < 1 else "tốt"
                out.append(
                    FlipCondition(
                        factor="ads_effect",
                        flip_at=round(x, 3),
                        base_value=1.0,
                        unit="hệ số",
                        text=(
                            f"Nếu ads hiệu quả {word} hơn ước lượng {abs(x - 1) * 100:.0f}%"
                            f" → {after}"
                        ),
                    )
                )
                break

    # 4. restock delay (days; negative = earlier than planned)
    plans = [p for s in inp.stock_skus if s.in_campaign for p in s.restock_plans]
    if plans:
        start_day = to_local(inp.start).date()
        earliest = -max((p[0] - start_day).days for p in plans)
        base_d = round(main.restock_delay)
        for rng_ in (range(base_d - 1, earliest - 1, -1), range(base_d + 1, 8)):
            for d in rng_:
                val = _diff(
                    resim([pair.best, pair.runner], Perturb(restock_delay=float(d)), SENS_SAMPLES),
                    pair,
                )
                if (val > 0) != (base > 0):
                    if d < 0:
                        txt = (
                            "Nếu hàng về trong hôm nay"
                            if d == earliest
                            else f"Nếu hàng về sớm {-d} ngày"
                        )
                    else:
                        txt = f"Nếu hàng về trễ từ {d} ngày"
                    out.append(
                        FlipCondition(
                            factor="restock_delay_days",
                            flip_at=float(d),
                            base_value=float(base_d),
                            unit="ngày",
                            text=f"{txt} → {after}",
                        )
                    )
                    break
            if out and out[-1].factor == "restock_delay_days":
                break
    return out


# ---------------------------------------------------------------------- recommendation
def _hm(t: datetime) -> str:
    loc = to_local(t)
    return f"{loc:%H}:00 {loc:%d/%m}"


def build_recommendation(
    run: SimRun,
    resim: Resim,
    *,
    with_flips: bool = True,
) -> tuple[Recommendation, Selection]:
    inp = run.inputs
    params = inp.params
    sel = select(run)
    lab, conf_reasons = confidence(inp)
    params.num("decision_min_prob")  # record every parameter of §9 in param_version
    params.num("decision_min_gain_vnd")
    ref = inputs_ref(inp)
    rid = new_id("rec")
    if sel.none_meets_goal:
        lines: list[str] = []
        for i, r in enumerate(run.runs):
            if sel.p_target[i] is not None:
                lines.append(f"{r.action.label_vi()}: {sel.p_target[i]:.0%}")
        reasons: list[str] = ["Các lựa chọn này chưa giải quyết được mục tiêu"]
        if lines:
            reasons.append(f"Xác suất bán đủ {inp.goal.target_units} sp: " + "; ".join(lines))
        reasons += [n for n in sel.notes.values()][:2]
        return (
            Recommendation(
                recommendation_id=rid,
                campaign_id=inp.campaign_id,
                status="none_meets_goal",
                best=None,
                runner_up=None,
                p_best_beats_runner_up=None,
                expected_gain_vnd=None,
                zone_bar=None,
                flip_conditions=[],
                confidence=lab,
                reasons=reasons + conf_reasons[:1],
                inputs_ref=ref,
            ),
            sel,
        )
    best = run.runs[sel.ranked[0]]
    runner = run.runs[sel.ranked[1]] if len(sel.ranked) > 1 else None
    p_best: float | None = None
    gain: float | None = None
    status: Literal["recommend", "undetermined"] = "undetermined"
    if runner is not None:
        sb = best.units_sold if sel.metric == "units_sold" else best.j
        sr = runner.units_sold if sel.metric == "units_sold" else runner.j
        p_best = float(np.mean(sb > sr))
        gain = float(np.mean(best.j) - np.mean(runner.j))
        min_p = params.num("decision_min_prob")
        if sel.metric == "units_sold":
            ok = p_best >= min_p and float(np.mean(sb - sr)) >= 1.0
        else:
            need = max(params.num("decision_min_gain_vnd"), 0.05 * abs(float(np.mean(best.j))))
            ok = p_best >= min_p and gain >= need
        status = "recommend" if ok else "undetermined"
    else:
        status = "recommend"
    bar, bar_reason = zone_bar(run, resim)
    partner = runner
    if sel.metric == "units_sold":
        # clear_stock ranks by units; the money trade-off that can flip is "clear vs keep"
        keep = run.by_key().get("pause")
        if keep is not None and keep.feasible and keep is not best:
            partner = keep
    flips = flip_conditions(run, best, partner, resim) if (with_flips and partner) else []

    # reasons
    reasons = []
    by = run.by_key()
    cont = by.get("continue", best)
    main = inp.sku(inp.main_sku) if inp.main_sku else None
    if main is not None:
        so = stockout_hour(inp, cont.first_lost_t[main.sku_id])
        dem = float(np.median(cont.demand_by_sku[main.sku_id]))
        stock_n = main.stock0 + float(inp.restock_matrix()[inp.stock_skus.index(main)].sum())
        if so is not None:
            reasons.append(
                f"Hàng {main.sku_id} sẽ hết khoảng {_hm(so)} (nhu cầu ~{dem:.0f} sp, tồn"
                f" {stock_n:.0f} sp): ads không bán thêm được khi hết hàng"
            )
        else:
            reasons.append(
                f"Nhu cầu {main.sku_id} dự kiến ~{dem:.0f} sp trong {inp.T} giờ, tồn"
                f" {stock_n:.0f} sp: còn hàng tới hết hạn"
            )
        m0 = float(main.m[0])
        price0 = float(main.price[0])
        day = to_local(inp.start)
        margin = f"Ở giá {day:%d.%m} ({format_vnd(round(price0))}) mỗi sp {main.sku_id} lãi"
        margin += f" {format_vnd(round(m0))}"
        if m0 > 0:
            margin += f"; ads chỉ có lời khi iROAS ≥ {price0 / m0:.1f}"
        reasons.append(margin)
    if any(MUST_RUN in [c for c, _ in r.violations] for r in run.runs):
        reasons.append("Không được tắt hẳn vì đã cam kết với sàn trong khung flash sale")
    if runner is not None and gain is not None and p_best is not None:
        if sel.metric == "units_sold":
            du = float(np.mean(best.units_sold - runner.units_sold))
            reasons.append(
                f"{best.action.label_vi()} bán thêm ~{du:.1f} sp so với"
                f" {runner.action.label_vi()} (xác suất {p_best:.0%}), chênh tiền"
                f" {format_vnd(round(gain))}"
            )
        else:
            reasons.append(
                f"{best.action.label_vi()} lợi hơn {runner.action.label_vi()} khoảng"
                f" {format_vnd(round(gain))} (xác suất {p_best:.0%})"
            )
    if bar_reason:
        reasons.append(bar_reason)
    if status == "undetermined" and runner is not None:
        reasons.append("Chênh lệch chưa đủ rõ để đề xuất chắc chắn")
    if not flips and partner is not None and with_flips:
        reasons.append("Kết luận giữ nguyên trong khoảng bất định hiện tại")
    reasons += conf_reasons[:2]
    rec = Recommendation(
        recommendation_id=rid,
        campaign_id=inp.campaign_id,
        status=status,
        best=best.action,
        runner_up=runner.action if runner is not None else None,
        p_best_beats_runner_up=p_best,
        expected_gain_vnd=round(gain) if gain is not None else None,
        zone_bar=bar,
        flip_conditions=flips,
        confidence=lab,
        reasons=reasons,
        inputs_ref=ref,
        created_at=utcnow(),
    )
    return rec, sel


def blocked_recommendation(inp: SimInputs) -> Recommendation:
    """Missing cost / price: nothing is simulated, result labelled ``scenario``."""
    return Recommendation(
        recommendation_id=new_id("rec"),
        campaign_id=inp.campaign_id,
        status="undetermined",
        best=None,
        runner_up=None,
        p_best_beats_runner_up=None,
        expected_gain_vnd=None,
        zone_bar=None,
        flip_conditions=[],
        confidence="scenario",
        reasons=[*inp.blocked_reasons, "Chưa tính được lợi nhuận nên chưa so sánh các hành động"],
        inputs_ref=inputs_ref(inp),
    )


def inputs_ref(inp: SimInputs) -> InputsRef:
    return InputsRef(
        forecast_ids=inp.forecast_ids,
        estimate_id=inp.iroas.estimate_id,
        param_version=inp.params.versions,
        goal_id=inp.goal.goal_id,
        data_as_of=inp.data_as_of,
        panel_version=inp.panel_version,
        iroas_source="estimate" if inp.iroas_source == "estimate" else "prior",
    )


# ---------------------------------------------------------------------- persistence
def persist(
    conn: duckdb.DuckDBPyConnection,
    out: SimOutput,
    inp: SimInputs,
    *,
    overrides: dict[str, object],
    samples: int,
    seed: int,
    requested_by: str,
) -> RecommendationChanged | None:
    """Write ``scenarios``, ``scenario_results``, ``recommendations``; the previous active
    recommendation of the campaign gets ``superseded_by`` (never deleted). Returns the
    ``RecommendationChanged`` event when best action or status changed."""
    rec = out.recommendation
    now = utcnow()
    conn.execute(
        "INSERT INTO scenarios (scenario_id, campaign_id, goal_id, start_at, horizon_hours,"
        " param_version, overrides, inputs_ref, samples, seed, requested_by, created_at,"
        " input_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            out.scenario_id,
            inp.campaign_id,
            inp.goal.goal_id,
            inp.start,
            inp.T,
            json.dumps(inp.params.versions),
            json.dumps(overrides),
            rec.inputs_ref.model_dump_json(),
            samples,
            seed,
            requested_by,
            now,
            out.input_hash,
        ],
    )
    seen: set[str] = set()
    for r in out.results:
        if r.action.key in seen:
            continue
        seen.add(r.action.key)
        conn.execute(
            "INSERT INTO scenario_results (scenario_id, action, feasible, violations, objective,"
            " contribution, spend, units_sold, leftover_units, leftover_value, stockout_hour_p50,"
            " per_sku) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                out.scenario_id,
                r.action.model_dump_json(),
                r.feasible,
                r.violations,
                r.objective.model_dump_json(),
                r.contribution.model_dump_json(),
                r.spend.model_dump_json(),
                r.units_sold.model_dump_json(),
                r.leftover_units.model_dump_json(),
                r.leftover_value.model_dump_json(),
                r.stockout_hour_p50,
                json.dumps([s.model_dump(mode="json") for s in r.per_sku]),
            ],
        )
    prev = conn.execute(
        "SELECT recommendation_id, status, best_action FROM recommendations WHERE campaign_id = ?"
        " AND superseded_by IS NULL ORDER BY created_at DESC LIMIT 1",
        [inp.campaign_id],
    ).fetchone()
    best_json = rec.best.model_dump_json() if rec.best else None
    conn.execute(
        "INSERT INTO recommendations (recommendation_id, scenario_id, campaign_id, status,"
        " best_action, runner_up, p_best, expected_gain_vnd, zone_bar, flip_conditions,"
        " confidence, reasons, superseded_by, created_at, input_hash)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
        [
            rec.recommendation_id,
            out.scenario_id,
            inp.campaign_id,
            rec.status,
            best_json,
            rec.runner_up.model_dump_json() if rec.runner_up else None,
            rec.p_best_beats_runner_up,
            rec.expected_gain_vnd,
            rec.zone_bar.model_dump_json() if rec.zone_bar else None,
            json.dumps([f.model_dump(mode="json") for f in rec.flip_conditions]),
            rec.confidence,
            rec.reasons,
            now,
            out.input_hash,
        ],
    )
    conn.execute(
        "UPDATE recommendations SET superseded_by = ? WHERE campaign_id = ?"
        " AND superseded_by IS NULL AND recommendation_id <> ?",
        [rec.recommendation_id, inp.campaign_id, rec.recommendation_id],
    )
    if prev is None:
        return RecommendationChanged(
            campaign_id=inp.campaign_id, old=None, new=rec.model_dump(mode="json")
        )
    old_best = json.loads(prev[2]) if isinstance(prev[2], str) else prev[2]
    new_best = json.loads(best_json) if best_json else None
    if prev[1] != rec.status or old_best != new_best:
        return RecommendationChanged(
            campaign_id=inp.campaign_id,
            old={"recommendation_id": prev[0], "status": prev[1], "best": old_best},
            new=rec.model_dump(mode="json"),
        )
    return None
