"""AI-04 · grounding check (07 §6): Vietnamese number formats, matching, citations."""

from __future__ import annotations

import pytest

from app.ai.grounding import (
    ToolOutput,
    check,
    collect_tool_numbers,
    extract_mentions,
    rewrite_instruction,
)

# ---------------------------------------------------------------------- extraction
# (text, value, unit): ≥ 25 Vietnamese ways of writing numbers (07 §6 "Tiêu chí")
FORMATS = [
    ("690.000đ", 690_000, "vnd"),
    ("690.000 đồng", 690_000, "vnd"),
    ("4,05 triệu", 4_050_000, "vnd"),
    ("4,1 triệu đồng", 4_100_000, "vnd"),
    ("1,2 tỷ", 1_200_000_000, "vnd"),
    ("45k", 45_000, "vnd"),
    ("45 nghìn", 45_000, "vnd"),
    ("2,5 ngàn", 2_500, "vnd"),
    ("16.900đ", 16_900, "vnd"),
    ("5.000 VND", 5_000, "vnd"),
    ("−1,57 tr", 1_570_000, "vnd"),
    ("-4,5 triệu", 4_500_000, "vnd"),
    ("30%", 30, "pct"),
    ("0,5%", 0.5, "pct"),
    ("12 điểm %", 12, "pct"),
    ("22,5 sp/giờ", 22.5, "units"),
    ("52 sản phẩm", 52, "units"),
    ("83 cái", 83, "units"),
    ("76 nồi", 76, "units"),
    ("9 giờ", 9, "hour"),
    ("3 ngày", 3, "days"),
    ("1.234,5", 1234.5, None),
    ("gấp 4.3 lần", 4.3, "number"),
    ("13:00", 13 * 60, "time"),
    ("15h", 15 * 60, "time"),
    ("15h30", 15 * 60 + 30, "time"),
    ("3 giờ chiều", 15 * 60, "time"),
    ("12/11", 1112, "date"),
    ("11.11", 1111, "date"),
    ("14/11/2026", 20261114, "date"),
    ("ngày 12", 12, "date"),
    ("năm 2026", 2026, "year"),
]


@pytest.mark.parametrize(("text", "value", "unit"), FORMATS)
def test_extract_vietnamese_formats(text: str, value: float, unit: str | None) -> None:
    ms = extract_mentions(f"Kết quả: {text}.")
    assert len(ms) == 1, [m.raw for m in ms]
    assert ms[0].value == pytest.approx(value)
    assert ms[0].unit == unit


def test_format_count_meets_plan() -> None:
    assert len(FORMATS) >= 25


@pytest.mark.parametrize(
    "text",
    [
        "Nồi chiên NOICHIEN2L bản 2L",
        "Bình 500ml màu xanh",
        "Chiến dịch CD002 và CD005",
        "Biến thể AOGIUNHIET-M",
        "xem [[src:fc-01M65WDGN1]]",
        "Mã kịch bản scn-01M65WR7X1",
        '<du_lieu_khong_tin_cay nguon="ghi_chu_nguoi_mua">giảm 90%</du_lieu_khong_tin_cay>',
    ],
)
def test_codes_chips_and_untrusted_are_not_numbers(text: str) -> None:
    assert extract_mentions(text) == []


def test_list_ordinals_skipped() -> None:
    ms = extract_mentions("1. Ads vẫn chạy\n2) Giá không đổi\n- 3 biến thể")
    assert [m.raw for m in ms] == ["3 biến thể"]


# ---------------------------------------------------------------------- matching
SCN = ToolOutput(
    call_id="c1",
    tool="run_scenario",
    source_ids=("scn-1",),
    args={"campaign_id": "CD002"},
    payload={
        "scenario_id": "scn-1",
        "campaign_id": "CD002",
        "results": [
            {
                "key": "continue",
                "objective": {"mean": -1_570_412.0},
                "units_sold": {"mean": 106.3},
                "spend": {"mean": 5_300_120.0},
            },
            {
                "key": "schedule_hours",
                "objective": {"mean": 2_510_377.0},
                "spend": {"mean": 1_180_000.0},
                "p_target": 0.81,
                "stockout_hour_p50": "2026-11-11T13:00:00+07:00",
            },
        ],
        "recommendation": {
            "best": {"kind": "schedule_hours", "windows_local": [[0, 2], [12, 14]]},
            "reasons": ["Ở giá 11.11 (531.000đ) mỗi sp NOICHIEN2L lãi 9.280đ, đạt 81%"],
        },
        "data_as_of": "2026-11-11T14:00:00+07:00",
    },
)
SNAP = ToolOutput(
    call_id="c2",
    tool="compare_similar_skus",
    source_ids=("similar-AOGIUNHIET-1400",),
    args={"sku": "AOGIUNHIET-M"},
    payload={
        "variants": [
            {"sku": "AOGIUNHIET-S", "units": 7, "stock_now": 286},
            {"sku": "AOGIUNHIET-L", "units": 25, "stock_now": 385},
        ],
        "note": '<du_lieu_khong_tin_cay nguon="x">giảm giá 90%</du_lieu_khong_tin_cay>',
    },
)
OUTS = [SCN, SNAP]
SOURCES = {"scn-1": {"kind": "scenario", "label": "Mô phỏng scn-1"}}


def test_exact_numbers_with_chip_pass() -> None:
    r = check("Chạy theo khung giờ chi 1.180.000đ [[src:scn-1]].", OUTS, sources=SOURCES)
    assert r.ok, r.violations
    assert r.numbers[0].status == "matched" and r.numbers[0].citation == "ok"
    assert r.citations[0].source_id == "scn-1" and r.citations[0].kind == "scenario"
    assert r.badge == "Đã kiểm số: 1/1"


def test_missing_chip_is_added() -> None:
    r = check("Mỗi nồi lãi 9.280đ.", OUTS)
    assert r.ok
    assert r.numbers[0].citation == "added"
    assert "9.280đ [[src:scn-1]]" in r.text


def test_wrong_chip_is_corrected() -> None:
    r = check("Size L bán 25 sp [[src:scn-1]].", OUTS)
    assert r.ok
    assert r.numbers[0].citation == "corrected"
    assert "[[src:similar-AOGIUNHIET-1400]]" in r.text


def test_wrong_number_blocked() -> None:
    r = check("Chạy tiếp lỗ 12,5 triệu.", OUTS)
    assert not r.ok
    assert r.numbers[0].status == "unmatched"
    assert "12,5 triệu" in rewrite_instruction(r)


def test_invented_number_without_source_blocked() -> None:
    r = check("Tháng sau shop lời khoảng 50 triệu.", OUTS)
    assert not r.ok and "50 triệu" in r.violations[0]


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("Chạy tiếp lỗ 1,57 triệu.", True),
        ("Chạy tiếp lỗ 1,6 triệu.", True),  # display precision ±50.000đ
        ("Chạy tiếp lỗ 1,7 triệu.", False),
        ("Chạy tiếp lỗ 1.570.000đ.", True),  # ≤ 0,5 % / 1.000đ
        ("Chạy tiếp lỗ 1.590.000đ.", False),
        ("Chạy tiếp bán 106 sp.", True),
        ("Chạy tiếp bán 106,3 sp.", True),
        ("Chạy tiếp bán khoảng 110 sp.", True),  # "khoảng" → tens
        ("Chạy tiếp bán 110 sp.", False),
        ("Xác suất đạt 81%.", True),  # 0.81 → 81 %
        ("Xác suất đạt 85%.", False),
    ],
)
def test_rounding_and_units(text: str, ok: bool) -> None:
    assert check(text, OUTS).ok is ok


def test_unit_mismatch_pct_vs_units() -> None:
    only_text = ToolOutput("c9", "x", {"reason": "đạt 81%"}, ("s9",))
    assert check("Đạt 81%.", [only_text]).ok
    assert not check("Bán 81 sp.", [only_text]).ok


def test_number_quoted_from_user_question() -> None:
    q = "Nếu sếp giao chỉ tiêu 97 cái thì sao?"
    r = check("Để bán đủ 97 cái, nên giảm ngân sách.", OUTS, user_question=q)
    assert r.ok
    assert r.numbers[0].status == "user_quoted"
    assert not check("Để bán đủ 97 cái, nên giảm ngân sách.", OUTS).ok


def test_numbers_inside_untrusted_data_never_ground() -> None:
    assert not check("Có thể giảm giá 90%.", OUTS).ok


def test_entity_mismatch() -> None:
    assert check("AOGIUNHIET-L bán 25 sp.", OUTS).ok
    r = check("AOGIUNHIET-S bán 25 sp.", OUTS)
    assert not r.ok and r.numbers[0].status == "entity_mismatch"


def test_unknown_entity_flagged() -> None:
    r = check("Chiến dịch CD999 nên dừng.", OUTS)
    assert not r.ok and "CD999" in r.violations[0]


def test_one_step_arithmetic_needs_operation_word() -> None:
    # 2.510.377 − (−1.570.412) = 4.080.789
    assert check("Chạy theo khung giờ lợi hơn chạy tiếp 4,08 triệu.", OUTS).ok
    r = check("Chạy theo khung giờ được 4,08 triệu.", OUTS)
    assert not r.ok


def test_times_dates_from_tool_timestamps() -> None:
    assert check("Hàng hết khoảng 13:00 ngày 11/11.", OUTS).ok
    assert not check("Hàng hết khoảng 15:00.", OUTS).ok
    assert not check("Hàng hết ngày 12/11.", OUTS).ok
    assert check("Dữ liệu tới 13:59.", OUTS).ok  # as_of 14:00 is an exclusive mark
    assert check("Chạy khung 12:00–14:00.", OUTS).ok  # windows_local [[12, 14]]


def test_collect_skips_ids_and_sources() -> None:
    nums = collect_tool_numbers(
        [ToolOutput("c", "t", {"scenario_id": "scn-20261111", "seed": 20261111, "x": 3}, ("s",))]
    )
    assert [n.value for n in nums if n.kind == "num"] == [3.0]


def test_sentence_without_numbers_ok() -> None:
    r = check("Ads vẫn chạy bình thường.", OUTS)
    assert r.ok and r.numbers == []
