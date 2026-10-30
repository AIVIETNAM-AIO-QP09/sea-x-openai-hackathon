"""Demand censored by stock (FC-02, plan 03 §4).

Stockout hours do not show demand (``units_gross`` is capped by stock). The base level is
estimated on in-stock hours only::

    L̂ = Σ_{t ∉ stockout} y_t / Σ_{t ∉ stockout} P_h(t)·W_w(t)·E(t)·(1 − disc_t)^β

and daily demand is rebuilt as::

    demand_adj(d) = Σ_{t ∈ d, in stock} y_t + Σ_{t ∈ d, stockout} max(y_t, L̂·P_h·W·E·…)

Hours with ``stockout_conf < 0.7`` (interpolated stock) count half in the level estimate.
All functions are vectorised over ``[sku, day, hour]`` and only see data before the origin.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArr = npt.NDArray[np.float64]
BoolArr = npt.NDArray[np.bool_]

LOW_CONF = 0.7
LOW_CONF_WEIGHT = 0.5
LEVEL_WINDOW_DAYS = 14
MIN_EXPECTED_SHARE = 0.3  # Σ expected share of in-stock hours needed for a local level


@dataclass(frozen=True)
class CensoredDays:
    """Per ``[sku, day]`` results of :func:`adjust_demand`."""

    demand_adj: FloatArr  # censoring-corrected daily demand
    raw: FloatArr  # Σ units_gross (what was sold)
    level: FloatArr  # local level L̂ (units per unit of expected share), trailing window
    expected_share: FloatArr  # Σ_h P·W·E·price over present hours (≈ W·E·price for a full day)
    stockout_hours: FloatArr  # number of stockout hours in the day
    instock_share: FloatArr  # Σ expected share of in-stock hours


def level_weights(instock: BoolArr, conf: FloatArr) -> FloatArr:
    """Weight of each hour in the level estimate: 0 stockout, 0.5 low-confidence stock."""
    w = instock.astype(np.float64)
    return np.where(conf < LOW_CONF, w * LOW_CONF_WEIGHT, w)


def _trailing_sum(a: FloatArr, window: int) -> FloatArr:
    """Sum over the trailing ``window`` days (including the day) along the last axis."""
    c = np.cumsum(a, axis=-1)
    out = c.copy()
    out[..., window:] = c[..., window:] - c[..., :-window]
    return out


def _ffill(a: FloatArr) -> FloatArr:
    """Forward-fill NaN along the last axis (vectorised); leading NaN stay NaN."""
    mask = np.isnan(a)
    idx = np.where(~mask, np.arange(a.shape[-1]), 0)
    np.maximum.accumulate(idx, axis=-1, out=idx)
    out = np.take_along_axis(a, idx, axis=-1)
    out[np.isnan(out)] = np.nan
    return out


def adjust_demand(
    y: FloatArr,
    present: BoolArr,
    stockout: BoolArr,
    conf: FloatArr,
    expected: FloatArr,
    *,
    censoring: bool = True,
    window: int = LEVEL_WINDOW_DAYS,
) -> CensoredDays:
    """``y``, ``present``, ``stockout``, ``conf``, ``expected`` are ``[S, D, 24]``.

    ``expected`` is the relative expected demand of each hour (``P_h·W·E·price``). With
    ``censoring=False`` every present hour counts as in stock (the "uncorrected" variant
    used to show the effect of the correction, 03 §10)."""
    pres = present.astype(np.float64)
    so = (stockout & present) if censoring else np.zeros_like(present)
    instock = present & ~so
    wl = level_weights(instock, conf) if censoring else pres
    exp_p = expected * pres
    a = np.sum(y * wl, axis=2)
    b = np.sum(exp_p * wl, axis=2)
    ra = _trailing_sum(a, window)
    rb = _trailing_sum(b, window)
    level = np.where(rb >= MIN_EXPECTED_SHARE, ra / np.maximum(rb, 1e-12), np.nan)
    level = np.nan_to_num(_ffill(level), nan=0.0)
    raw = np.sum(y * pres, axis=2)
    if censoring:
        y_in = np.sum(y * instock, axis=2)
        y_so = np.sum(y * so, axis=2)
        c = np.sum(expected * so, axis=2)
        demand_adj = y_in + np.maximum(level * c, y_so)
    else:
        demand_adj = raw
    return CensoredDays(
        demand_adj=demand_adj,
        raw=raw,
        level=level,
        expected_share=np.sum(exp_p, axis=2),
        stockout_hours=np.sum(so, axis=2).astype(np.float64),
        instock_share=np.sum(expected * instock, axis=2),
    )
