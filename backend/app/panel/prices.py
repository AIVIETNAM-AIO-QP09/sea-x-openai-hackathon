"""Effective price per SKU × VN day → ``price_events`` (plan 02 §6.3, PNL-01).

* Day with non-cancelled orders: ``eff_price`` = median ``unit_price``, ``list_price``
  = median ``list_price`` of those orders (``source='orders'``).
* Day without orders: carry the last known prices forward (``carried_forward``).
* Day with a ``committed_price`` sale commitment (11.11): the committed price wins
  (``commitment``); list price is the carried one.
* Before the first order of a SKU there is no row (eff price unknown).

``discount_pct = 1 − eff/list`` clipped to [0, 1] (a price above list = no discount).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

PRICE_COLUMNS = ["sku_id", "day_local", "list_price", "eff_price", "discount_pct", "source"]


def build_price_events(
    observed: pd.DataFrame,
    days: list[date],
    commitments: pd.DataFrame | None = None,
    fallback_list_price: dict[str, int] | None = None,
) -> pd.DataFrame:
    """``observed``: columns sku_id, day_local (date), list_price, eff_price (medians of the
    day). ``commitments``: sku_id, day_local, value_int. Returns rows for ``days`` from each
    SKU's first known price on."""
    if not days:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    obs = observed.copy()
    obs["source"] = "orders"
    if commitments is not None and not commitments.empty:
        com = commitments.rename(columns={"value_int": "eff_price"})[
            ["sku_id", "day_local", "eff_price"]
        ].copy()
        com["list_price"] = np.nan
        com["source"] = "commitment"
        obs = pd.concat(
            [
                obs[
                    ~obs.set_index(["sku_id", "day_local"]).index.isin(
                        com.set_index(["sku_id", "day_local"]).index
                    )
                ],
                com,
            ],
            ignore_index=True,
        )
    if obs.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    day_set = set(days)
    obs = obs[obs["day_local"].isin(day_set)]
    out = []
    fallback = fallback_list_price or {}
    for sku, g in obs.groupby("sku_id", sort=True):
        g = g.set_index("day_local").sort_index()
        first = g.index.min()
        idx = [d for d in days if d >= first]
        f = g.reindex(idx)
        src = f["source"].where(f["source"].notna(), "carried_forward")
        f["eff_price"] = f["eff_price"].astype(float).ffill()
        lp = f["list_price"].astype(float).ffill().bfill()
        if lp.isna().all() and str(sku) in fallback:
            lp = lp.fillna(float(fallback[str(sku)]))
        f["list_price"] = lp.fillna(f["eff_price"])
        f["source"] = src
        f["sku_id"] = sku
        out.append(f.reset_index(names="day_local"))
    res = pd.concat(out, ignore_index=True)
    res["eff_price"] = res["eff_price"].round().astype("int64")
    res["list_price"] = res["list_price"].round().astype("int64")
    lp = res["list_price"].where(res["list_price"] > 0)
    res["discount_pct"] = (1.0 - res["eff_price"] / lp).clip(0.0, 1.0).fillna(0.0)
    return res[PRICE_COLUMNS]
