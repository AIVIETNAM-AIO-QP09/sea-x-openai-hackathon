"""Forecast metrics (FC-09, plan 03 §7.2).

With ``y`` actual and ``ŷ`` = p50, summed over the (SKU, day) cells of a backtest:

* ``WAPE = Σ|y − ŷ| / Σ y`` at SKU × day (hours summed first; ŷ = median of the day total)
* ``Bias = (Σŷ − Σy) / Σy``
* ``Pinball_q = mean(max(q·(y − ŷ_q), (q − 1)·(y − ŷ_q)))`` at hour level, q ∈ {0.1, 0.5, 0.9}
* ``Coverage`` = share of (SKU, day) with ``y ∈ [p10, p90]`` of the day total (target 80 %)

WAPE only uses SKUs selling ≥ 1 unit/day (``wape_eligible``); sparse SKUs are judged on
pinball.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

FloatArr = npt.NDArray[np.float64]
QUANTILES = (0.1, 0.5, 0.9)
MIN_WAPE_RATE = 1.0  # units/day


def wape(y: FloatArr, yhat: FloatArr) -> float | None:
    s = float(np.sum(y))
    return float(np.sum(np.abs(y - yhat)) / s) if s > 0 else None


def bias(y: FloatArr, yhat: FloatArr) -> float | None:
    s = float(np.sum(y))
    return float((np.sum(yhat) - s) / s) if s > 0 else None


def pinball(y: FloatArr, q_pred: FloatArr, q: float) -> float:
    d = y - q_pred
    return float(np.mean(np.maximum(q * d, (q - 1) * d))) if d.size else 0.0


def pinball_sum(y: FloatArr, q_pred: FloatArr, q: float) -> float:
    d = y - q_pred
    return float(np.sum(np.maximum(q * d, (q - 1) * d)))


def coverage(y: FloatArr, lo: FloatArr, hi: FloatArr) -> float | None:
    return float(np.mean((y >= lo) & (y <= hi))) if y.size else None


@dataclass
class ScoreRow:
    model_id: str
    backtest: str
    demand_group: str
    context: str
    n_skus: int
    n_sku_days: int
    wape: float | None
    bias: float | None
    pinball_10: float | None
    pinball_50: float | None
    pinball_90: float | None
    coverage: float | None
    is_champion: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def key_metric(self) -> float:
        """WAPE when defined, else pinball_50 (sparse groups)."""
        if self.wape is not None:
            return self.wape
        return self.pinball_50 if self.pinball_50 is not None else float("inf")


DAY_COLUMNS = (
    "model_id",
    "backtest",
    "sku_id",
    "demand_group",
    "context",
    "day",
    "y",
    "p10",
    "p50",
    "p90",
    "mean",
    "wape_eligible",
    "pb10",
    "pb50",
    "pb90",
    "n_hours",
)


def aggregate(
    days: pd.DataFrame, backtest: str, group: str, context: str, model_id: str
) -> ScoreRow:
    """Aggregate per-(SKU, day) records (columns ``DAY_COLUMNS``) into one score row.
    SKU-days without any in-stock hour carry no information and are dropped."""
    days = days[days["n_hours"] > 0]
    el = days[days["wape_eligible"]]
    y, p50 = el["y"].to_numpy(float), el["p50"].to_numpy(float)
    nh = float(days["n_hours"].sum())
    pb = {q: (float(days[f"pb{int(q * 100)}"].sum()) / nh if nh > 0 else None) for q in QUANTILES}
    return ScoreRow(
        model_id=model_id,
        backtest=backtest,
        demand_group=group,
        context=context,
        n_skus=int(days["sku_id"].nunique()) if len(days) else 0,
        n_sku_days=len(days),
        wape=wape(y, p50) if len(el) else None,
        bias=bias(y, p50) if len(el) else None,
        pinball_10=pb[0.1],
        pinball_50=pb[0.5],
        pinball_90=pb[0.9],
        coverage=coverage(
            days["y"].to_numpy(float), days["p10"].to_numpy(float), days["p90"].to_numpy(float)
        ),
    )


def score_table(days: pd.DataFrame, *, by_group: bool = True) -> list[ScoreRow]:
    """Rows per (model, backtest, group, context); ``by_group=False`` pools the shop."""
    rows: list[ScoreRow] = []
    keys = ["model_id", "backtest", "context"] + (["demand_group"] if by_group else [])
    for key, part in days.groupby(keys, sort=True):
        k = dict(zip(keys, key if isinstance(key, tuple) else (key,), strict=True))
        rows.append(
            aggregate(
                part,
                str(k["backtest"]),
                str(k.get("demand_group", "all")),
                str(k["context"]),
                str(k["model_id"]),
            )
        )
    return rows
