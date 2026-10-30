"""Confidence labels (FC-09, plan 03 §7.3).

``scope`` = score of the champion on the **same group and context** as the request (11.11
is ``double_day`` → scores of ``dd_*`` backtests, never normal days).

[DEV] 03 §7.3 has a code block (``scope is None → scenario``) and a sentence ("no score for
this context → reference + reason"). Both are kept: never scored for the group at all →
``scenario``; scored for the group but not this context → ``reference`` with the reason
"chưa kiểm ở bối cảnh này". Decision log M2 C6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

Label = Literal["verified", "reference", "scenario"]

MIN_HISTORY_DAYS = 14
MAX_WAPE = 0.30
COVERAGE_BAND = (0.72, 0.88)
MIN_SKU_DAYS = 30


class ScopeLike(Protocol):
    @property
    def wape(self) -> float | None: ...

    @property
    def coverage(self) -> float | None: ...

    @property
    def n_sku_days(self) -> int | None: ...


def confidence_label(scope: ScopeLike | None, history_days: int, drift_active: bool) -> Label:
    """Exactly the rule of 03 §7.3."""
    if history_days < MIN_HISTORY_DAYS or scope is None:
        return "scenario"
    ok = (
        scope.wape is not None
        and scope.wape <= MAX_WAPE
        and scope.coverage is not None
        and COVERAGE_BAND[0] <= scope.coverage <= COVERAGE_BAND[1]
        and (scope.n_sku_days or 0) >= MIN_SKU_DAYS
    )
    label: Label = "verified" if ok else "reference"
    if drift_active and label == "verified":
        label = "reference"
    return label


@dataclass
class LabelDecision:
    label: Label
    reasons: list[str]


def decide_label(
    scope: ScopeLike | None,
    history_days: int,
    drift_active: bool,
    *,
    group_scored: bool,
    nowcast: bool = False,
) -> LabelDecision:
    """Label + Vietnamese reasons, including the two plan cases above and ``nowcast``
    (at most ``reference``)."""
    reasons: list[str] = []
    if history_days < MIN_HISTORY_DAYS:
        reasons.append(f"Chỉ có {history_days} ngày lịch sử (< {MIN_HISTORY_DAYS}): kịch bản")
        return LabelDecision("scenario", reasons)
    if scope is None:
        if group_scored:
            reasons.append("Chưa kiểm ở bối cảnh này")
            label: Label = "reference"
        else:
            reasons.append("Mô hình chưa được backtest cho nhóm hàng này")
            label = "scenario"
    else:
        label = confidence_label(scope, history_days, drift_active)
        if label == "reference" and not drift_active:
            parts = []
            if scope.wape is None:
                parts.append("không đủ SKU ≥ 1 sp/ngày để tính WAPE")
            elif scope.wape > MAX_WAPE:
                parts.append(f"WAPE backtest {scope.wape:.0%} > {MAX_WAPE:.0%}")
            if scope.coverage is None or not (
                COVERAGE_BAND[0] <= scope.coverage <= COVERAGE_BAND[1]
            ):
                cov = "—" if scope.coverage is None else f"{scope.coverage:.0%}"
                parts.append(f"độ phủ khoảng p10–p90 {cov} ngoài 72–88%")
            if (scope.n_sku_days or 0) < MIN_SKU_DAYS:
                parts.append(f"chỉ {scope.n_sku_days or 0} SKU-ngày để kiểm")
            if parts:
                reasons.append("Tham khảo: " + "; ".join(parts))
        if drift_active:
            reasons.append("Đang có cảnh báo lệch dự báo")
    if nowcast and label == "verified":
        label = "reference"
    return LabelDecision(label, reasons)
