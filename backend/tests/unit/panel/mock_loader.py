"""Test-only loader: raw mock-data CSV/JSON → canonical tables (schema.sql).

The real adapters (ING-01..06) and SKU matching (ING-08) are written in parallel,
so the panel tests load the canonical tables themselves, the simple way:

* orders: drop PII columns, drop exact duplicate rows, map statuses (02 §2.1);
* ads: the "Thời gian" column is UTC (known mock trap, offset +7) → read as UTC;
* inventory: internal code → platform SKU via the answer key ``sku_that.csv``
  (TESTS ONLY — app/ never reads it); negative stock → NULL + ``negative``;
  "Nhập {qty}" in the note → ``restock_receipts``;
* combo components from the onboarding seed (``repo.seed_bundles``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb
import pandas as pd

from app.core.ids import new_id
from app.warehouse import repo
from app.warehouse.db import migrate

REPO_DIR = Path(__file__).resolve().parents[4]
MOCK_OUT = REPO_DIR / "mock-data" / "out"
VN = "Asia/Ho_Chi_Minh"

STATUS = {
    "Hoàn thành": ("completed", True),
    "Trả hàng/Hoàn tiền": ("returned", True),
    "Đã hủy": ("cancelled", True),
    "Đang giao": ("shipping", False),
    "Chờ lấy hàng": ("awaiting_pickup", False),
    "Chờ xác nhận": ("pending", False),
}
AD_STATUS = {"Đang chạy": "running", "Tạm dừng": "paused", "Hết ngân sách": "budget_exhausted"}
ORDER_COLS = [
    "Mã đơn hàng",
    "Ngày đặt hàng",
    "Trạng thái đơn hàng",
    "Tên sản phẩm",
    "Tên phân loại hàng",
    "SKU phân loại hàng",
    "Giá gốc",
    "Giá ưu đãi",
    "Số lượng",
    "Tổng tiền hàng",
]
RECEIPT_RE = re.compile(r"Nhập\s+(\d+)")


def answer_dir(size: str) -> Path:
    return MOCK_OUT / size / "ground_truth"


def _csv(path: Path, **kw: object) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", **kw)  # type: ignore[call-overload]


def _vn_to_utc(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format="%Y-%m-%d %H:%M").dt.tz_localize(VN).dt.tz_convert("UTC")


def _batch(
    conn: duckdb.DuckDBPyConnection, source: str, name: str, as_of: pd.Timestamp | None, n: int
) -> str:
    bid = new_id()
    conn.execute(
        "INSERT INTO ingest_batches (batch_id, source_type, file_name, file_sha256, received_at,"
        " as_of, row_count, mode, status) VALUES (?, ?, ?, ?, now(), ?, ?, 'history', 'ok')",
        [bid, source, name, bid, None if as_of is None else as_of.to_pydatetime(), n],
    )
    return bid


def _insert(conn: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    cols = ", ".join(f'"{c}"' for c in df.columns)
    conn.register("_src", df)
    try:
        conn.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _src")
    finally:
        conn.unregister("_src")


def _orders(raw: pd.DataFrame, batch_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = raw.drop_duplicates()
    raw = raw.drop_duplicates(subset=["Mã đơn hàng"], keep="last")
    st = raw["Trạng thái đơn hàng"].map(STATUS)
    orders = pd.DataFrame(
        {
            "order_id": raw["Mã đơn hàng"].astype(str),
            "ordered_at": _vn_to_utc(raw["Ngày đặt hàng"]),
            "status": [s[0] for s in st],
            "status_final": [s[1] for s in st],
            "batch_id": batch_id,
        }
    )
    lines = pd.DataFrame(
        {
            "order_id": raw["Mã đơn hàng"].astype(str),
            "line_no": 1,
            "sku_id": raw["SKU phân loại hàng"].astype(str),
            "qty": raw["Số lượng"].astype(int),
            "list_price": raw["Giá gốc"].astype(int),
            "unit_price": raw["Giá ưu đãi"].astype(int),
            "line_total": raw["Giá ưu đãi"].astype(int) * raw["Số lượng"].astype(int),
        }
    )
    return orders, lines


def _ads(raw: pd.DataFrame, batch_id: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campaign_id": raw["Mã chiến dịch"].astype(str),
            # mock trap: the column is UTC already
            "hour_utc": pd.to_datetime(raw["Thời gian"], format="%Y-%m-%d %H:%M").dt.tz_localize(
                "UTC"
            ),
            "status": raw["Trạng thái"].map(AD_STATUS).fillna("unknown"),
            "daily_budget": raw["Ngân sách ngày"].astype(int),
            "spend": raw["Chi phí"].astype(int),
            "impressions": raw["Lượt hiển thị"].astype(int),
            "clicks": raw["Lượt click"].astype(int),
            "attributed_orders": raw["Đơn hàng"].astype(int),
            "attributed_revenue": raw["Doanh thu"].astype(int),
            "batch_id": batch_id,
        }
    ).drop_duplicates(["campaign_id", "hour_utc"], keep="last")


def _inventory(
    raw: pd.DataFrame, code_to_sku: dict[str, str], batch_id: str, hourly: bool
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if hourly:
        at = _vn_to_utc(raw["Thời điểm cập nhật"])
        day = (
            pd.to_datetime(raw["Thời điểm cập nhật"], format="%Y-%m-%d %H:%M") - pd.Timedelta("1h")
        ).dt.date
    else:
        d = pd.to_datetime(raw["Ngày"], format="%Y-%m-%d")
        at = (d + pd.Timedelta(days=1)).dt.tz_localize(VN).dt.tz_convert("UTC")
        day = d.dt.date
    on_hand = pd.to_numeric(raw["Tồn thực tế"], errors="coerce")
    neg = on_hand < 0
    note = raw["Ghi chú"].astype(object).where(raw["Ghi chú"].notna(), None)
    snaps = pd.DataFrame(
        {
            "sku_id": raw["Mã nội bộ"].map(code_to_sku),
            "snapshot_at": at,
            "on_hand": pd.array(on_hand.where(~neg), dtype="Int64"),
            "quality_flag": ["negative" if x else None for x in neg],
            "note": note,
            "granularity": "hour" if hourly else "day",
            "batch_id": batch_id,
        }
    )
    rec_rows = []
    for sku, d_, n_ in zip(snaps["sku_id"], day, note, strict=True):
        if n_:
            for q in RECEIPT_RE.findall(str(n_)):
                rec_rows.append({"sku_id": sku, "received_on": d_, "qty": int(q)})
    rec = pd.DataFrame(rec_rows, columns=["sku_id", "received_on", "qty"])
    if not rec.empty:
        rec = rec.groupby(["sku_id", "received_on"], as_index=False)["qty"].sum()
    return snaps, rec


def load_mock(conn: duckdb.DuckDBPyConnection, size: str = "nho", *, live: bool = False) -> None:
    """Load ``mock-data/out/<size>`` history (and the 11.11 day when ``live``)."""
    base = MOCK_OUT / size
    migrate(conn)
    truth = _csv(answer_dir(size) / "sku_that.csv", dtype=str, keep_default_na=False)
    code_to_sku = dict(zip(truth["ma_noi_bo"], truth["sku"], strict=True))
    cutoff = pd.Timestamp("2026-11-11 00:00", tz=VN).tz_convert("UTC")
    end_live = cutoff + pd.Timedelta(days=1)

    # catalogue
    products = (
        truth.assign(
            product_id=[
                repo.derive_product_id(s, is_bundle=bool(c))
                for s, c in zip(truth["sku"], truth["thanh_phan_combo"], strict=True)
            ]
        )
        .groupby("product_id", as_index=False)["ten_san_pham"]
        .first()
        .rename(columns={"ten_san_pham": "name"})
    )
    _insert(conn, "products", products)
    skus = pd.DataFrame(
        {
            "sku_id": truth["sku"],
            "product_id": [
                repo.derive_product_id(s, is_bundle=bool(c))
                for s, c in zip(truth["sku"], truth["thanh_phan_combo"], strict=True)
            ],
            "variant_name": truth["phan_loai"].replace("", None),
            "list_price": truth["gia_niem_yet"].astype(int),
            "is_bundle": truth["thanh_phan_combo"] != "",
        }
    )
    _insert(conn, "skus", skus)
    repo.seed_bundles(conn)

    # orders
    raw = _csv(base / "don_hang_seller_center.csv", usecols=ORDER_COLS, dtype={"Mã đơn hàng": str})
    b = _batch(conn, "orders", "don_hang_seller_center.csv", cutoff, len(raw))
    orders, lines = _orders(raw, b)
    if live:
        raw_l = _csv(
            base / "live_11_11" / "don_hang_seller_center.csv",
            usecols=ORDER_COLS,
            dtype={"Mã đơn hàng": str},
        )
        bl = _batch(conn, "orders", "live/don_hang_seller_center.csv", end_live, len(raw_l))
        o2, l2 = _orders(raw_l, bl)
        orders = pd.concat([orders, o2], ignore_index=True)
        lines = pd.concat([lines, l2], ignore_index=True)
    _insert(conn, "orders", orders)
    _insert(conn, "order_lines", lines)

    # inventory
    raw_inv = _csv(base / "ton_kho_google_sheet.csv", dtype={"Ghi chú": str})
    bi = _batch(conn, "inventory", "ton_kho_google_sheet.csv", cutoff, len(raw_inv))
    snaps, rec = _inventory(raw_inv, code_to_sku, bi, hourly=False)
    if live:
        raw_il = _csv(base / "live_11_11" / "ton_kho_google_sheet.csv", dtype={"Ghi chú": str})
        bil = _batch(conn, "inventory", "live/ton_kho_google_sheet.csv", end_live, len(raw_il))
        s2, r2 = _inventory(raw_il, code_to_sku, bil, hourly=True)
        # live notes repeat every hour of the day: keep the first hour that shows them
        snaps = pd.concat([snaps, s2], ignore_index=True)
        rec = pd.concat([rec, r2.drop_duplicates(["sku_id", "received_on"])], ignore_index=True)
        rec = rec.drop_duplicates(["sku_id", "received_on"], keep="first")
    _insert(conn, "inventory_snapshots", snaps)
    _insert(conn, "restock_receipts", rec)

    # campaigns + ads
    camps = json.loads((base / "cau_truc_chien_dich.json").read_text(encoding="utf-8"))
    _insert(
        conn,
        "campaigns",
        pd.DataFrame(
            {
                "campaign_id": [c["ma_chien_dich"] for c in camps],
                "name": [c["ten_chien_dich"] for c in camps],
                "type": [c["loai"] for c in camps],
                "daily_budget": [int(c["ngan_sach_ngay"]) for c in camps],
                "started_at": _vn_to_utc(pd.Series([c["bat_dau"] for c in camps])),
                "sku_level_control": [len(c["sku"]) == 1 for c in camps],
            }
        ),
    )
    _insert(
        conn,
        "campaign_skus",
        pd.DataFrame(
            [{"campaign_id": c["ma_chien_dich"], "sku_id": s} for c in camps for s in c["sku"]]
        ),
    )
    raw_ads = _csv(base / "bao_cao_ads.csv")
    ba = _batch(conn, "ads", "bao_cao_ads.csv", None, len(raw_ads))
    ads = _ads(raw_ads, ba)
    if live:
        raw_al = _csv(base / "live_11_11" / "bao_cao_ads.csv")
        bal = _batch(conn, "ads", "live/bao_cao_ads.csv", None, len(raw_al))
        ads = pd.concat([ads, _ads(raw_al, bal)], ignore_index=True)
    _insert(conn, "ad_hourly", ads)

    # sale program: flash windows + committed prices
    prog = json.loads((base / "chuong_trinh_sale.json").read_text(encoding="utf-8"))
    day = prog["ngay"]
    rows = []
    for w in prog["khung_flash_sale"]:
        a, z = w.split("-")
        ws = pd.Timestamp(f"{day} {a}", tz=VN).tz_convert("UTC")
        we = pd.Timestamp(f"{day} {z}", tz=VN).tz_convert("UTC")
        rows.append({"kind": "flash_window", "sku_id": None, "value_int": None, "ws": ws, "we": we})
    for c in prog["cam_ket"]:
        rows.append(
            {
                "kind": "committed_price",
                "sku_id": c["sku"],
                "value_int": int(c["gia_cam_ket"]),
                "ws": None,
                "we": None,
            }
        )
    for r in rows:
        conn.execute(
            "INSERT INTO sale_commitments (commitment_id, program, day_local, kind, sku_id,"
            " value_int, window_start, window_end) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                new_id(),
                prog["chuong_trinh"],
                pd.Timestamp(day).date(),
                r["kind"],
                r["sku_id"],
                r["value_int"],
                None if r["ws"] is None else r["ws"].to_pydatetime(),
                None if r["we"] is None else r["we"].to_pydatetime(),
            ],
        )
