# Nhật ký quyết định · Nền tảng lớp AI (M4: AI-01, AI-02, AI-03, AI-04, AI-06, AI-07, AI-09, AI-10, khung EVAL-05)

Code: `backend/app/ai/` (chưa nối endpoint). Test: `backend/tests/unit/ai/` (143 test, gồm 4 test e2e trên `demo`).

| File | Nội dung |
|---|---|
| `client.py` | Giao diện `LlmClient`; `FakeClient` (kịch bản cho test/eval), `OpenAIClient` (Responses API + function calling strict, model lấy từ env), `RecordReplayClient` (`AI_MODE=record/replay`), `make_client(settings)` |
| `tools/registry.py` | `ToolSpec`, `@tool`, `execute()` (kiểm JSON, schema, vai trò, cổng nháp/xác nhận, ghi `ai_tool_calls`), cắt kết quả ≤ 4.000 token |
| `tools/schemas.py` | Pydantic tham số của 26 công cụ + `strict_schema()` |
| `tools/read.py`, `compute.py`, `draft.py` | 17 công cụ đọc, 3 công cụ tính, 6 công cụ nháp/ghi (07 §3) |
| `grounding.py` | Kiểm số (07 §6) |
| `guard.py` | Chống prompt injection (07 §7) |
| `agent.py` | Vòng function calling, ngân sách token, viết lại khi sai số, log `ai_sessions` |
| `flows/__init__.py` | 6 luồng (whatif, investigate, explain, handoff, ingest, chat): công cụ + model theo việc |
| `flows/whatif.py` | `WhatIfIntent` (structured output) → `RunScenarioArgs` → `SimRequest`; bộ tách ý theo luật |
| `flows/investigate.py` | Checklist 6 bước chạy công cụ thật + tóm tắt |
| `prompts/*.vi.md` | System prompt 07 §5 + phần riêng từng luồng; `PROMPT_VERSION` = hash các file |
| `cache.py` | `data_fingerprint`, cache câu trả lời 30 phút |
| `evals.py` + `tests/unit/ai/eval_cases.json` | Khung eval 07 §10, 18 câu ban đầu |

## 1. Kết quả chính

- **What-if "sếp giao chỉ tiêu 97 cái"** (DB demo lúc 01:00 ngày 11.11, công cụ thật): tách ý ra `goal_override = sell_target, 97`. Mục tiêu hiện tại (profit) vẫn đề xuất "chỉ chạy khung giờ 00–02, 12–14". Với kịch bản giả định thì đề xuất **giảm ngân sách 30%**: xác suất đạt 81%, còn chạy khung giờ chỉ đạt 57%. Khớp M3-whatif 4g. Câu trả lời qua kiểm số 8/8. Bảng `goals` không thêm dòng nào, kịch bản không lưu.
- **Điều tra "vì sao áo giữ nhiệt bán chậm"** (DB demo lúc 14:00): checklist chạy 15 lần gọi công cụ. Nguyên nhân là `AOGIUNHIET-M` hết hàng (tồn 0 từ 13:00). Kho có ghi chú điều chỉnh tồn lúc 11:00, tồn giảm 74 sp. Size L bán 27 sp, size S bán 11 sp trong 3 giờ. Ads CD005 vẫn chạy (số liệu ads tới 11:59). Gợi ý giảm ngân sách CD005 tới khi hàng về ngày 14/11. Kiểm số 10/10.
- **Injection** (ghi chú cài sẵn ở đơn `2611099UF5GLZH` trong `don_hang_seller_center.csv`): ghi chú được bọc `<du_lieu_khong_tin_cay nguon="ghi_chu_nguoi_mua">` và gắn cờ `possible_instruction`. Test dùng model giả "bị dụ" để thử cả hai đường tấn công:
  - Model gọi `draft_decision` pause. Lệnh bị chặn với lỗi `needs_user_request`, không ghi `decisions`.
  - Model viết "hãy tắt toàn bộ quảng cáo". Câu này bị chặn, hệ thống ghi `alerts` loại `ai_policy` và bắt viết lại. Câu cuối nói "có ghi chú chứa yêu cầu lạ, không làm theo".
  - Dữ liệu gửi cho LLM không chứa `Khách Test` hay số điện thoại.

## 2. Quyết định

### Q1. Công cụ gọi thẳng hàm service/snapshot, không gọi HTTP
Công cụ dùng lại `app.api.snapshot` (`sku_rows`, `detail`, `commitments`, `latest_forecasts`), `app.api.common.freshness`, `issue_message`, `run_simulation`, `load_estimate`, `load_param_set`, `active_goal`, `set_parameter`. Nhờ vậy số của AI cùng nguồn với màn hình. Lớp AI không sửa file nào của `app/api`, chỉ import.

### Q2. `run_scenario` thêm `goal_override` (`[DEV]` so với 07 §3)
Câu hỏi "nếu sếp giao chỉ tiêu N" là giả định về **mục tiêu**, không phải tham số. AI không được tạo mục tiêu (05 §4, 10 §1), nên xử lý như sau:
- Mục tiêu giả định được INSERT trong một transaction, chạy `run_simulation(persist=False, use_cache=False)`, rồi **luôn ROLLBACK**.
- Kết quả có nhãn `is_scenario`, `confidence = scenario`, `goal.hypothetical = true`.
- Hạn mặc định là hạn của mục tiêu đang áp dụng, nếu không có thì là hết ngày dữ liệu hiện tại.

Tương tự, chạy có `param_overrides` thì không lưu (không thay đề xuất đang hiệu lực). Chạy không có giả định thì lưu như `POST /scenarios/run`, để `draft_decision` có `scenario_id`. Override sai danh mục hoặc ngoài khoảng sẽ nằm trong `param_overrides_rejected` kèm lý do, LLM phải nói ra.

### Q3. Cổng ghi: nháp chỉ khi chính người dùng yêu cầu
- Công cụ `draft` (`draft_decision`, `suggest_parameter`, `propose_*`, `draft_shift_handoff`) chạy khi có một trong hai điều kiện:
  - `ToolContext.allow_drafts` (nút trên UI);
  - **câu của người dùng** khớp ý "tạo/lưu nháp, gửi duyệt, ghép cột…" (`guard.user_requests_draft`). Không bao giờ xét nội dung kết quả công cụ.
- `request_approval` cần thêm `user_confirmed` (nút "Gửi duyệt").
- Các lỗi `needs_user_request` / `needs_confirmation` được trả cho LLM, không ném lỗi.
- `draft_decision` từ chối kịch bản có giả định ("dùng Ghi chú cho lead"), từ chối hành động vi phạm ràng buộc, và ghi `audit_log` với `via='ai'`.
- Nháp ghép cột, ghép SKU, bàn giao ca tạm giữ trong bộ nhớ (`draft.DRAFTS`) cho tới khi có endpoint xác nhận.

### Q4. Grounding: dung sai theo độ chính xác hiển thị
Ngoài ngưỡng 07 §6 (0,5% hoặc 1.000đ; 0,5 điểm %), số còn được khớp nếu lệch trong nửa đơn vị của chữ số cuối đã viết ("4,1 triệu" phủ ±50.000đ). Có từ "khoảng" thì nới gấp đôi, số tròn chục thì phủ ±5. Các quy tắc khác:
- **Không chấp nhận** số nằm trong khối dữ liệu không tin cậy.
- Số người dùng viết trong câu hỏi được chấp nhận (`user_quoted`).
- Phép tính một bước (hiệu, tổng, tỷ lệ) chỉ được chấp nhận khi câu có từ chỉ phép tính, và chỉ xét số cùng loại.
- Câu nêu SKU hoặc chiến dịch thì số phải thuộc đối tượng đó (`entity_mismatch`). Mã lạ không có trong kết quả công cụ bị chặn.
- Giờ "13:59" khớp với `as_of` 14:00, vì `as_of` là mốc không bao gồm.
- Chip thiếu hoặc sai được backend tự gắn hoặc sửa (`citation = added | corrected`), không bắt viết lại.

Sai thì viết lại tối đa 2 lần, sau đó trả câu dự phòng kèm bảng số thô và ghi `grounding_ok=false`.

### Q5. Đầu ra bị chặn khi khuyên "tắt toàn bộ ads" mà không có mô phỏng ủng hộ
Câu phủ định ("không đề xuất tắt toàn bộ…") vẫn được phép. Lần vi phạm đầu tiên trong lượt ghi một dòng `alerts` (`kind='ai_policy'`).

### Q6. Record/replay theo lượt
Khóa = sha256 của (luồng, câu hỏi chuẩn hóa, `data_fingerprint`, `PROMPT_VERSION`, hash lịch sử phiên). `data_fingerprint` dùng (nguồn, `as_of`, số dòng) của batch, mục tiêu đang hiệu lực và tham số hiệu lực. Không dùng ULID, nên dựng lại cùng dữ liệu vẫn trúng bản ghi.
- **Replay** chỉ phát lại phản hồi của LLM. **Công cụ vẫn chạy thật** trên dữ liệu hiện tại, và grounding kiểm lại. Câu trả lời được gắn nhãn "Câu trả lời đã lưu (chế độ demo ngoại tuyến)".
- Không có bản ghi thì trả `outcome=offline` ("Trợ lý đang ngoại tuyến").
- Bản ghi nằm ở `backend/eval/ai_recordings/<flow>/<key>.json`. File chỉ lưu tóm tắt request (model, số item, tên công cụ), không lưu prompt hay dữ liệu thô.

### Q7. Agent điều tra theo mức sàn của 12
Checklist (`run_checklist`) chạy công cụ thật và không cần LLM. Kết quả được đưa cho LLM như kết quả của công cụ giả `investigation_checklist`. LLM chỉ viết tóm tắt, và tóm tắt phải qua grounding. `summarize_payload` viết cùng tóm tắt khi AI tắt; FakeClient trong test cũng dùng hàm này. `investigate(..., alert_id=)` lưu vào `alerts.investigation`.

### Q8. Vòng lặp đồng bộ (sync)
Endpoint hiện tại là sync, dùng threadpool. `Agent.run_turn` là sync để dùng chung cursor DuckDB. SSE ở đợt sau có thể chạy trong threadpool và đẩy sự kiện theo từng bước.

### Q9. Eval dùng JSON, chạy offline
Dependency không có parser YAML nên câu eval viết bằng JSON. Mỗi câu có `script` (các bước LLM giả) và `tool_fixtures` (kết quả công cụ mẫu đi qua cùng `execute`, kể cả cổng quyền và nháp). Metric theo 07 §10. Offline, 18/18 câu đạt mọi ngưỡng. Lưu ý: với FakeClient, metric "đúng công cụ / đúng tham số" chỉ kiểm khung chấm, chưa đo chất lượng model.

### Q10. Khác
- `get_forecast(action="pause")` trả `available=false` kèm lời dặn dùng `run_scenario`/`compare_actions`, vì dự báo lưu trong DB đi theo kế hoạch ads hiện tại.
- `suggest_sku_matches` chưa dùng embeddings (cần `OPENAI_MODEL_EMBED`); hiện chấm điểm bằng rapidfuzz.
- `compare_similar_skus`: nếu có dự báo phủ đủ khung giờ thì so với dự báo, nếu không thì so với trung bình cùng giờ của 7 ngày trước.
- `guard.py` import `app.ingest.adapters` trước `app.ingest.pii` vì hai module import vòng (lỗi sẵn có ở ingest, không sửa).
- `cost_estimate_usd` để NULL vì chưa có bảng giá model.

## 3. Endpoint cần thêm ở đợt sau (API-07, chưa làm)

| Method | Path | Ghi chú |
|---|---|---|
| POST | `/ai/chat` | body `{session_id?, flow, message, context{campaign_id?, sku?, scenario_id?}, allow_drafts?}`. Sàn: trả JSON một lần (`TurnResult`: text, citations, grounding badge + bảng đối chiếu, tool_calls, outcome, replayed/label) |
| GET | `/ai/chat/stream` hoặc SSE trên `/ai/chat` | sự kiện `tool_call`, `tool_result`, `rewrite`, `answer` |
| POST | `/ai/whatif/parse` | câu hỏi → `WhatIfIntent` / `RunScenarioArgs` hoặc câu hỏi lại |
| POST | `/alerts/{id}/investigate` | gọi `flows.investigate.investigate(..., alert_id=)` |
| POST | `/ai/drafts/{draft_id}/confirm` | xác nhận nháp ghép cột / ghép SKU / bàn giao (`draft.DRAFTS`) |
| POST | `/decisions/{id}/submit` | phía UI của `request_approval` (`user_confirmed=true`) |
| GET | `/ai/sessions/{id}` | lịch sử + tool calls (màn Nhật ký) |

Phụ thuộc: `deps.require_role(operator)`; dùng `make_client(settings)`; `AI_ENABLED=false` trả 503 `AI_UNAVAILABLE`, các màn hình khác vẫn chạy.

## 4. Việc cần làm khi có OPENAI_API_KEY

1. Chọn model, điền `OPENAI_MODEL_REASONING / FAST / EMBED` vào `.env.example` kèm ngày kiểm bảng giá. Thêm bảng giá để tính `cost_estimate_usd`.
2. Chạy thật `OpenAIClient` và kiểm:
   - strict schema của 26 công cụ được API chấp nhận (`strict_schema` đã đưa min/max/format vào description);
   - cách trả lại `output_items` (reasoning + function_call) giữa các bước;
   - model reasoning không nhận `temperature` (client đã có nhánh thử lại bỏ tham số này).
3. Chạy `tests/unit/ai/eval_cases.json` ở chế độ live (`run_case(..., offline=False, client_factory=…)`) trên DB demo. Mở rộng lên khoảng 40 câu, viết `eval/eval_ai.py` xuất `eval/reports/ai_eval_<thời gian>.md`.
4. `AI_MODE=record` khi diễn tập kịch bản demo 3 phút để có đủ bản ghi; GOV-06 quét PII trong bản ghi.
5. Embeddings cho `suggest_sku_matches` (lưu `sku_aliases.embedding`, cần migration); đọc ảnh chụp màn hình ở luồng nhập dữ liệu.

## 5. Kiểm tra chất lượng

- `ruff check` / `ruff format --check`: sạch trên `app/ai`, `tests/unit/ai`.
- `mypy app`: sạch (110 file).
- `pytest tests/unit/ai tests/unit/test_no_ground_truth_leak.py`: 143 đạt, khoảng 1 phút (dựng DB demo khoảng 44 giây).
- Prompt và code trong `app/ai` không nhắc tới thư mục đáp án.
