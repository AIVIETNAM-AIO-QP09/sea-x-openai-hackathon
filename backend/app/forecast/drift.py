"""CUSUM drift detection (FC-07, plan 03 §9).

Run each hour during the day for SKUs with a forecast, on in-stock hours only::

    z_t  = (y_t − λ_t) / sqrt(λ_t + λ_t²/k)
    S⁺_t = max(0, S⁺_{t−1} + z_t − 0.5)
    S⁻_t = max(0, S⁻_{t−1} − z_t − 0.5)

Hours with ``λ < 0.25`` are skipped too (see ``MIN_LAMBDA``). Alarm when ``S⁺ > 5``
(above forecast) or ``S⁻ > 5`` (below); both reset to 0 after an alarm. Stockout hours are
skipped, so an empty shelf reads as "hết hàng", not as falling demand (``AOGIUNHIET-M`` on
11.11). ``up`` → ``nowcast`` for 24 h; ``down`` → only an alert with a checklist for the AI
agent (no automatic "trend is over").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

import numpy as np
import numpy.typing as npt

from app.core.events import DriftDetected

FloatArr = npt.NDArray[np.float64]
BoolArr = npt.NDArray[np.bool_]

THRESHOLD = 5.0
SLACK = 0.5
# [DEV] hours whose forecast is below this are skipped: with λ ≈ 0.05 a single order gives
# z ≈ 4, the Normal approximation behind the standardised residual does not hold (night
# hours). Decision log M2 C7.
MIN_LAMBDA = 0.25
NOWCAST_HOURS = 24
DOWN_CHECKLIST = (
    "Giá hoặc voucher có đổi không",
    "Có biến thể nào hết hàng không",
    "Quảng cáo có bị tắt hoặc hết ngân sách không",
    "Dữ liệu đơn có bị trễ không",
)


@dataclass
class DriftAlarm:
    sku_id: str
    hour: datetime  # UTC start of the hour that triggered the alarm
    direction: Literal["up", "down"]
    stat: float
    checklist: list[str] = field(default_factory=list)

    @property
    def nowcast_until(self) -> datetime | None:
        if self.direction != "up":
            return None
        return self.hour + timedelta(hours=1 + NOWCAST_HOURS)

    def event(self) -> DriftDetected:
        return DriftDetected(sku_id=self.sku_id, direction=self.direction, stat=self.stat)


@dataclass
class CusumTrace:
    s_pos: FloatArr
    s_neg: FloatArr
    z: FloatArr
    alarms: list[tuple[int, Literal["up", "down"], float]]


def cusum(
    y: FloatArr,
    lam: FloatArr,
    k: float,
    instock: BoolArr | None = None,
    *,
    threshold: float = THRESHOLD,
    slack: float = SLACK,
    min_lambda: float = MIN_LAMBDA,
) -> CusumTrace:
    """CUSUM over hourly actuals ``y`` vs forecast mean ``lam`` (same length)."""
    n = len(y)
    use = np.ones(n, dtype=bool) if instock is None else np.asarray(instock, dtype=bool)
    sp = np.zeros(n)
    sn = np.zeros(n)
    zz = np.zeros(n)
    alarms: list[tuple[int, Literal["up", "down"], float]] = []
    s_pos = s_neg = 0.0
    kk = max(float(k), 1e-6)
    for t in range(n):
        if use[t] and np.isfinite(y[t]) and float(lam[t]) >= min_lambda:
            lt = float(lam[t])
            z = (float(y[t]) - lt) / np.sqrt(lt + lt * lt / kk)
            zz[t] = z
            s_pos = max(0.0, s_pos + z - slack)
            s_neg = max(0.0, s_neg - z - slack)
            if s_pos > threshold:
                alarms.append((t, "up", s_pos))
                s_pos = s_neg = 0.0
            elif s_neg > threshold:
                alarms.append((t, "down", s_neg))
                s_pos = s_neg = 0.0
        sp[t], sn[t] = s_pos, s_neg
    return CusumTrace(s_pos=sp, s_neg=sn, z=zz, alarms=alarms)


def scan(
    sku_id: str,
    hours: Sequence[datetime],
    y: FloatArr,
    lam: FloatArr,
    k: float,
    instock: BoolArr | None = None,
) -> list[DriftAlarm]:
    trace = cusum(y, lam, k, instock)
    out: list[DriftAlarm] = []
    for t, direction, stat in trace.alarms:
        out.append(
            DriftAlarm(
                sku_id=sku_id,
                hour=hours[t],
                direction=direction,
                stat=float(stat),
                checklist=list(DOWN_CHECKLIST) if direction == "down" else [],
            )
        )
    return out


def active_up(alarms: Sequence[DriftAlarm], at: datetime) -> set[str]:
    """SKUs whose last ``up`` alarm still keeps ``nowcast`` on at ``at``."""
    out: set[str] = set()
    for a in alarms:
        until = a.nowcast_until
        if until is not None and a.hour < at <= until:
            out.add(a.sku_id)
    return out
