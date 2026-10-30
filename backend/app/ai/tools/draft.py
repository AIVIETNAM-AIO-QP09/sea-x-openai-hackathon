"""Draft / write tools (07 §3): they never take effect by themselves.

* ``draft_decision`` → a ``decisions`` row in state ``draft`` (``created_via='ai'``, 10 §3);
  only for a persisted scenario without assumptions, and only a feasible action.
* ``request_approval`` → ``draft`` → ``pending_approval``; needs the UI confirmation flag.
* ``suggest_parameter`` → ``parameters`` row with ``set_by='ai_suggested'`` (not effective
  until a person confirms it, 05 §3).
* ``propose_column_mapping`` / ``propose_sku_matches`` / ``draft_shift_handoff`` → drafts
  kept in :data:`DRAFTS` (in memory) until the confirmation endpoints exist (M4-ai.md).

The registry runs these only when the user asked for a draft in their own words or the UI
set ``allow_drafts`` (07 §7: data content can never trigger a write).
"""

from __future__ import annotations

import contextlib
import json
import threading
from datetime import timedelta
from typing import Any

from app.ai import guard
from app.ai.tools._util import iso, now_data, parse_ts, require_campaign
from app.ai.tools.registry import Source, ToolContext, ToolData, tool
from app.ai.tools.schemas import (
    ColumnMappingArgs,
    DraftDecisionArgs,
    HandoffArgs,
    ProposeSkuArgs,
    RequestApprovalArgs,
    SuggestParameterArgs,
)
from app.api.common import parse_json
from app.core.errors import ConstraintViolation, NotFound, StateConflict, ValidationFailed
from app.core.ids import new_id
from app.core.timeutil import utcnow
from app.economics.parameters import set_parameter
from app.simulator.schemas import ActionSpec
from app.warehouse.repo import fetch_all, fetch_one

_LOCK = threading.Lock()
DRAFTS: dict[str, dict[str, Any]] = {}

MONEY_FIELDS = {
    "list_price", "effective_price", "line_total", "daily_budget", "spend",
    "attributed_revenue", "unit_cost", "packaging_cost",
}  # fmt: skip
PII_FIELDS = {"buyer_name", "buyer_phone", "buyer_address"}


def _store(kind: str, ctx: ToolContext, payload: dict[str, Any]) -> str:
    did = new_id(kind)
    with _LOCK:
        DRAFTS[did] = {
            "draft_id": did,
            "kind": kind,
            "session_id": ctx.session_id,
            "user_id": ctx.user_id,
            "created_at": utcnow().isoformat(),
            "status": "pending_confirmation",
            "payload": payload,
        }
    return did


def _audit(ctx: ToolContext, action: str, target_kind: str, target_id: str, after: Any) -> None:
    with contextlib.suppress(Exception):  # audit must not break the draft
        ctx.conn.execute(
            'INSERT INTO audit_log (id, "at", shop_id, actor, actor_role, via, action,'
            " target_kind, target_id, before, after, request_id) VALUES (?, ?, ?, ?, ?, 'ai',"
            " ?, ?, ?, NULL, ?, ?)",
            [
                new_id("aud"),
                utcnow(),
                ctx.settings.shop_id,
                ctx.user_id,
                ctx.role,
                action,
                target_kind,
                target_id,
                json.dumps(after, ensure_ascii=False, default=str),
                ctx.session_id,
            ],
        )


@tool(
    "draft_decision",
    "Tạo BẢN NHÁP quyết định cho một chiến dịch từ một kết quả mô phỏng (không có giả định)."
    " Người dùng phải xem và gửi duyệt.",
    DraftDecisionArgs,
    kind="draft",
)
def draft_decision(args: DraftDecisionArgs, ctx: ToolContext) -> ToolData:
    require_campaign(ctx.conn, args.campaign_id)
    scn = fetch_one(
        ctx.conn,
        "SELECT scenario_id, campaign_id, overrides, inputs_ref, input_hash FROM scenarios"
        " WHERE scenario_id = ?",
        [args.scenario_id],
    )
    if scn is None:
        raise NotFound(
            "Không có kịch bản này trong hệ thống (kịch bản giả định không lưu được thành quyết"
            " định; hãy dùng ghi chú cho lead).",
            scenario_id=args.scenario_id,
        )
    if scn["campaign_id"] != args.campaign_id:
        raise ValidationFailed("Kịch bản không thuộc chiến dịch này.")
    overrides = parse_json(scn["overrides"]) or {}
    if overrides:
        raise ValidationFailed(
            "Kịch bản có giả định nên không lưu thành quyết định; dùng 'Ghi chú cho lead'."
        )
    windows = [tuple(w) for w in args.action.windows_local] if args.action.windows_local else None
    try:
        action = ActionSpec(kind=args.action.kind, pct=args.action.pct, windows_local=windows)
    except ValueError as e:
        raise ValidationFailed(f"Hành động không hợp lệ: {e}") from e
    results = fetch_all(
        ctx.conn,
        "SELECT action, feasible, violations FROM scenario_results WHERE scenario_id = ?",
        [args.scenario_id],
    )
    match = None
    for r in results:
        a = ActionSpec.model_validate(parse_json(r["action"]))
        if a.key == action.key:
            match = r
    if match is None:
        raise ValidationFailed(f"Hành động {action.key} không có trong kịch bản.")
    if not match["feasible"]:
        raise ConstraintViolation(
            f"Hành động {action.label_vi()} vi phạm ràng buộc: {', '.join(match['violations'])}.",
            violations=list(match["violations"] or []),
        )
    rec = fetch_one(
        ctx.conn,
        "SELECT recommendation_id, best_action FROM recommendations WHERE scenario_id = ?",
        [args.scenario_id],
    )
    best = parse_json(rec["best_action"]) if rec else None
    best_key = ActionSpec.model_validate(best).key if best else None
    ref = parse_json(scn["inputs_ref"]) or {}
    did = new_id("dec")
    now = utcnow()
    ctx.conn.execute(
        "INSERT INTO decisions (id, kind, target_kind, target_id, action, state, rationale,"
        " override_of_recommendation, recommendation_id, recommended_action, scenario_id,"
        " data_as_of, input_hash, created_by, created_via, created_at) VALUES (?, 'ad_action',"
        " 'campaign', ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?, 'ai', ?)",
        [
            did,
            args.campaign_id,
            json.dumps(action.model_dump(mode="json")),
            args.rationale[:2000],
            best_key is not None and best_key != action.key,
            rec["recommendation_id"] if rec else None,
            json.dumps(best) if best else None,
            args.scenario_id,
            json.dumps({"data_as_of": ref.get("data_as_of")}),
            scn["input_hash"],
            ctx.user_id,
            now,
        ],
    )
    _audit(ctx, "decision.draft", "campaign", args.campaign_id, {"decision_id": did})
    return ToolData(
        data={
            "decision_id": did,
            "state": "draft",
            "action": action.model_dump(mode="json"),
            "action_label": action.label_vi(),
            "override_of_recommendation": best_key is not None and best_key != action.key,
            "message": "Đã tạo bản nháp. Người dùng cần xem và bấm Gửi duyệt.",
        },
        sources=[Source(id=did, kind="decision", label="Bản nháp quyết định")],
        requires_confirmation=True,
    )


@tool(
    "request_approval",
    "Chuyển bản nháp quyết định sang chờ lead duyệt. Chỉ chạy khi người dùng đã bấm Gửi duyệt.",
    RequestApprovalArgs,
    kind="write",
)
def request_approval(args: RequestApprovalArgs, ctx: ToolContext) -> ToolData:
    row = fetch_one(
        ctx.conn, "SELECT id, state, created_by FROM decisions WHERE id = ?", [args.decision_id]
    )
    if row is None:
        raise NotFound("Không có quyết định này.", decision_id=args.decision_id)
    if row["state"] != "draft":
        raise StateConflict(f"Quyết định đang ở trạng thái {row['state']}, không gửi duyệt được.")
    if row["created_by"] != ctx.user_id:
        raise StateConflict("Chỉ người tạo bản nháp mới gửi duyệt được.")
    blocking = ctx.conn.execute(
        "SELECT count(*) FROM data_quality_issues WHERE status = 'open' AND severity = 'error'"
        " AND entity_id IN (SELECT sku_id FROM campaign_skus WHERE campaign_id = (SELECT"
        " target_id FROM decisions WHERE id = ?))",
        [args.decision_id],
    ).fetchone()
    if blocking and int(blocking[0]) > 0:
        raise StateConflict("Còn vấn đề dữ liệu chặn (blocking), chưa gửi duyệt được.")
    ctx.conn.execute(
        "UPDATE decisions SET state = 'pending_approval', submitted_at = ? WHERE id = ?",
        [utcnow(), args.decision_id],
    )
    _audit(ctx, "decision.submit", "decision", args.decision_id, {"state": "pending_approval"})
    return ToolData(
        data={"decision_id": args.decision_id, "state": "pending_approval"},
        sources=[Source(id=args.decision_id, kind="decision", label="Quyết định chờ duyệt")],
        requires_confirmation=True,
    )


@tool(
    "suggest_parameter",
    "Gợi ý một giá trị tham số (ghi set_by=ai_suggested). Chưa có hiệu lực cho tới khi người"
    " dùng xác nhận.",
    SuggestParameterArgs,
    kind="draft",
)
def suggest_parameter(args: SuggestParameterArgs, ctx: ToolContext) -> ToolData:
    p = set_parameter(
        ctx.conn,
        args.key,
        args.value,
        scope=args.scope,
        scope_id=args.scope_id or "*",
        set_by="ai_suggested",
        reason=f"[AI gợi ý] {args.reason}"[:500],
    )
    _audit(ctx, "parameter.suggest", "parameter", args.key, {"version": p.version})
    return ToolData(
        data={
            "key": p.key,
            "scope": p.scope,
            "scope_id": p.scope_id,
            "suggested_value": p.value,
            "version": p.version,
            "set_by": p.set_by,
            "effective": False,
            "message": "Gợi ý chưa có hiệu lực; người dùng cần bấm Xác nhận.",
        },
        sources=[
            Source(id=f"param-{p.key}-v{p.version}", kind="parameter", label="Tham số AI gợi ý")
        ],
        requires_confirmation=True,
    )


@tool(
    "propose_column_mapping",
    "Đề xuất ghép cột của file vừa tải lên vào schema chuẩn. Người dùng phải xác nhận.",
    ColumnMappingArgs,
    kind="draft",
)
def propose_column_mapping(args: ColumnMappingArgs, ctx: ToolContext) -> ToolData:
    if (
        ctx.conn.execute(
            "SELECT 1 FROM ingest_batches WHERE batch_id = ?", [args.batch_id]
        ).fetchone()
        is None
    ):
        raise NotFound(f"Không có lần nạp {args.batch_id}.")
    rules = []
    mappings = []
    for m in args.mappings:
        d = m.model_dump()
        # hard rules run after the LLM (07 §4.1 step 4)
        if m.target_field in MONEY_FIELDS and m.transform != "parse_vnd":
            d["transform"] = "parse_vnd"
            rules.append(f"{m.source_column}: tiền luôn parse_vnd")
        if m.target_field in PII_FIELDS and m.transform != "strip_pii":
            d["transform"] = "strip_pii"
            rules.append(f"{m.source_column}: cột thông tin cá nhân luôn strip_pii")
        mappings.append(d)
    did = _store(
        "map", ctx, {"batch_id": args.batch_id, "file_kind": args.file_kind, "mappings": mappings}
    )
    return ToolData(
        data={"draft_id": did, "mappings": mappings, "rules_applied": rules},
        sources=[Source(id=did, kind="draft", label="Nháp ghép cột")],
        requires_confirmation=True,
    )


@tool(
    "propose_sku_matches",
    "Đề xuất ghép tên/mã hàng chưa ghép với SKU sàn. Người dùng phải xác nhận.",
    ProposeSkuArgs,
    kind="draft",
)
def propose_sku_matches(args: ProposeSkuArgs, ctx: ToolContext) -> ToolData:
    out = []
    for m in args.matches:
        alias = fetch_one(
            ctx.conn, "SELECT alias_id FROM sku_aliases WHERE alias_id = ?", [m.alias]
        )
        sku = ctx.conn.execute("SELECT 1 FROM skus WHERE sku_id = ?", [m.sku]).fetchone()
        out.append(
            {
                **m.model_dump(),
                "valid": alias is not None and sku is not None,
                "flag": "auto"
                if m.confidence >= 0.9
                else "check"
                if m.confidence >= 0.6
                else "low",
            }
        )
    did = _store("skumatch", ctx, {"batch_id": args.batch_id, "matches": out})
    return ToolData(
        data={"draft_id": did, "matches": out},
        sources=[Source(id=did, kind="draft", label="Nháp ghép SKU")],
        requires_confirmation=True,
    )


@tool(
    "draft_shift_handoff",
    "Soạn nháp ghi chú bàn giao ca: quyết định đã duyệt, việc chờ duyệt, cảnh báo mở, dữ liệu"
    " trễ. Người dùng sửa rồi lưu.",
    HandoffArgs,
    kind="draft",
)
def draft_shift_handoff(args: HandoffArgs, ctx: ToolContext) -> ToolData:
    end = parse_ts(args.to, now_data(ctx.conn))
    start = parse_ts(args.from_, end - timedelta(hours=8))
    decisions = fetch_all(
        ctx.conn,
        "SELECT id, target_id, action, state, rationale FROM decisions WHERE created_at >= ?"
        " ORDER BY created_at",
        [start],
    )
    alerts = fetch_all(
        ctx.conn,
        "SELECT id, kind, target_id, title, severity FROM alerts WHERE status = 'open'"
        " ORDER BY raised_at DESC LIMIT 20",
    )
    sections = {
        "approved": [d for d in decisions if d["state"] in ("approved", "sent", "verified")],
        "pending": [d for d in decisions if d["state"] in ("draft", "pending_approval")],
        "open_alerts": alerts,
    }
    for sec in ("approved", "pending"):
        for d in sections[sec]:
            d["action"] = parse_json(d["action"])
            d["rationale"] = guard.wrap(d["rationale"], "ly_do_quyet_dinh")
    did = _store("handoff", ctx, {"from": iso(start), "to": iso(end), **sections})
    return ToolData(
        data={"draft_id": did, "from": iso(start), "to": iso(end), **sections},
        sources=[Source(id=did, kind="draft", label="Nháp ghi chú bàn giao", as_of=iso(end))],
        requires_confirmation=True,
    )
