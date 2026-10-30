# M5 · Chuẩn bị demo (không phụ thuộc M4)

Phạm vi: độ trễ ads trên huy hiệu độ mới, script kiểm con số pitch (`backend/eval/pitch_numbers.py`), runbook demo ([docs/demo/runbook.md](../demo/runbook.md)). Phần live "nhảy tới giờ H" và cảnh báo thuộc M4 điều phối, chưa có trong runbook.

## Q1. Vì sao 01:00 ngày 11.11 Ads trễ 4 giờ, không phải 2 giờ

**Nguyên nhân: dữ liệu mock có một lỗ 3 giờ ads.** Không phải lỗi múi giờ, cách tính `as_of`, hay ngưỡng.

- Lịch sử giữ lại 3 giờ ads cuối (lỗi cài sẵn `do_tre_ads`, `config.dirty.adsLagHours = 3`): `bao_cao_ads.csv` dừng ở `2026-11-10 13:00` UTC = 20:00 VN, nên `as_of` ads lịch sử = **21:00 ngày 10/11**. Đơn và tồn tới 23:59.
- `live_11_11/bao_cao_ads.csv` và `_replay.json` bắt đầu ở 00:00 ngày 11/11 (`2026-11-10 17:00` UTC). 3 giờ 21:00–23:59 ngày 10/11 **không bao giờ về**.
- Phát lại giờ H: đơn tới H:59, ads tới (H − 2):59 (`adsLagHours = 2`). H = 0 và 1 chưa có dòng ads live nào, nên ads vẫn ở 21:00.

Đo bằng pipeline thật (lịch sử + `eval.live_replay.write_live_stream` + `ingest_live_delta`, rồi `app.api.common.freshness`):

| Giờ phát lại H | Đồng hồ dữ liệu | Ads `as_of` | Trễ | Trạng thái |
|---|---|---|---|---|
| 0 | 01:00 11/11 | 21:00 10/11 | 240 phút | stale |
| 1 | 02:00 | 21:00 10/11 | 300 phút | stale |
| 2 | 03:00 | 01:00 11/11 | 120 phút | fresh |
| 5 | 06:00 | 04:00 | 120 phút | fresh |

Đã loại trừ:
- **Múi giờ:** adapter áp +7 giờ đúng (lịch sử phát hiện `ADS_TZ_SHIFT`, live dùng offset đã xác nhận). Batch live ads ra `as_of` 18:00 UTC = 01:00 VN như mong đợi.
- **`as_of` = giờ bắt đầu hay giờ kết thúc:** `AdsAdapter` lấy giờ cuối + 1 giờ (mốc không bao gồm), cùng quy ước với đơn/tồn. Đúng.
- **Ngưỡng 180 phút:** đúng 06 §4 ("ads trễ sẵn 2 giờ"). Không đổi.
- **`demo_import` / `stage_live`:** cắt ads theo `stamp < until` (ads hiểu là UTC), **không trễ** 2 giờ. DB `demo_import --until 01:00` cho ads `as_of` 01:00, trễ **0 phút**. Lệch thiết kế theo chiều ngược lại, nhưng không phải nguồn của con số 240. Không sửa: nếu thêm trễ 2 giờ vào `stage_live`, DB 01:00 sẽ không có dòng ads live nào và cũng ra 240 phút.

**Kết luận: trễ 4 giờ lúc 01:00 là đúng với dữ liệu hiện có.** Huy hiệu "Dữ liệu Ads cũ hơn ngưỡng" nói thật. Thiết kế "trễ 2 giờ" chỉ đúng từ 03:00.

### Đã thử sửa ở mock-data, rồi hoàn tác vì đổi số pitch

Cách sửa đúng chỗ: bộ sinh đưa 3 giờ bị giữ của lịch sử vào luồng live, với giờ phát lại âm (−3 = 21:00 ngày 10/11). Patch (2 chỗ trong `mock-data/src/export.js`):

```js
if (ms >= this.t.cutoffMs - this.dirty.adsLagHours * HOUR) {
  this.stats.adsRowsHeldBack++;
  const line = csvLine(row);
  this.w.liveAds.writeLine(line);
  this.replay.ads.push([hourOf(ms) - 24, line]);
  return;
}
```

Sinh lại `demo` cho kết quả tất định: chỉ đổi `live_11_11/bao_cao_ads.csv` (+147 dòng), `_replay.json`, `manifest.json`. `replay.js`, `app/live/replay.py`, `eval/live_replay.py` đã lọc `h <= H − 2` nên tự nhận giờ âm. Sau sửa: trễ 2 giờ ở mọi giờ H.

`eval.demo_whatif --only 1,4g,5,8a` trước và sau patch:

| | Trước | Sau |
|---|---|---|
| [1] CD002 | schedule_hours 0-2,12-14, +3,99 tr vs continue, +1,23 tr vs giảm 50%, p = 1,00 | **như cũ** |
| [4g] | reduce_budget 0.3, +1,66 tr | như cũ |
| [5] | pause, +2,37 tr | như cũ |
| [8a] CD020 06/11 | pause (p 0,91, +107 k); **ZoneBar `pause_better`**, khoảng 0,67–1,21 vs x* 0,65 | pause (p 0,92, +108 k); **ZoneBar `undetermined`**, khoảng **0,62**–1,21 |
| iROAS CD002 (DB demo 01:00) | 4,42 [3,33–5,39] | 4,40 [3,33–5,40] |
| iROAS CD005 | 3,15 | 3,04 |

Lý do số đổi: 2 giờ ads thêm (21:00–22:00 ngày 10/11) đi vào `estimate_all` của DB 01:00, làm dịch nhẹ ước lượng chung. Con số pitch "ZoneBar CD020 06/11 → pause_better" bị lật (biên cũ chỉ 0,02 sp/giờ). Theo yêu cầu "đổi số thì dừng", **đã hoàn tác toàn bộ** (`export.js`, `out/demo`), repo như trước.

### Đề xuất cho chủ dự án (chọn một)

1. **Giữ nguyên, nói thật trên sân khấu** (khuyên dùng cho pitch 31/10). Lúc 01:00 huy hiệu Ads vàng/đỏ là đúng; câu nói: "Báo cáo ads về chậm, app nói thẳng số ads đang cũ". Cảnh phát lại bắt đầu từ 9 giờ thì Ads trễ đúng 2 giờ. Test `tests/unit/ingest/test_ads_lag_replay.py` ghi lại hành vi này.
2. **Áp patch ở trên** sau buổi pitch (hoặc trước, nếu đổi ví dụ ZoneBar). Khi áp: sinh lại `nho` và `demo`, xóa `KNOWN_GAP` trong test, chạy lại `eval.pitch_numbers`, đổi ví dụ ZoneBar sang bản 3 ngày CD020 06–09/11 (biên cũ 0,79 vs 0,72, cần đo lại).
3. Không đổi ngưỡng 180 phút cho "đẹp": ngưỡng đúng thiết kế, số 240 là sự thật của dữ liệu.

## Q2. `eval.pitch_numbers`: tái dùng eval có sẵn, không viết lại phép đo

- Dữ liệu: `eval.eval_data.run` (tự dựng DB tạm, đo cả thời gian nạp). Dự báo: `eval.eval_forecast.run` (nặng nhất, ~7–15 phút), đọc số từ `rep.checks` và `rep.data["labels"]`. iROAS: `eval.eval_ads.run` (chỉ lịch sử). What-if: `eval.demo_whatif.build_db`, `variants_cd002`, `run_variant`, `ads_table`. `/scenarios/run`: TestClient trên DB what-if, 4 lần với seed khác nhau (không trúng cache), lấy trung vị 3 lần sau.
- Cách đo từng cái giá: [4g] = E[J] cao nhất trong các phương án khả thi − E[J] đề xuất; cam kết flash = E[J] pause khi bỏ ràng buộc ([5]) − E[J] đề xuất [1]. Đúng cách tính trong M3-mo-phong "Sau sửa lỗi".
- Dung sai: tỷ lệ ghép SKU ± 0,5 điểm; WAPE ± 1,5 điểm; phân nhóm ± 1 điểm; nhãn tin cậy khớp đúng; iROAS trung vị ± 1 điểm; 40/49 ± 1 chiến dịch; coverage ± 2,1 điểm (= 1 chiến dịch trên 48); iROAS CD002 trong 4,35–4,55; tiền ± 0,1 triệu; p ≥ 0,99; thời gian theo ngưỡng (< 60 s, < 5 s, ≤ 0,5 s cho "~0,3 s"). Số nhạy với tải máy (thời gian) có ghi chú.
- `--reuse-db PATH` chỉ dùng cho what-if + API, và luôn chép sang thư mục tạm trước. Phần dữ liệu/dự báo/iROAS tự dựng DB để số khớp với nguồn pitch (lịch sử thuần, đo thời gian nạp).
- Một phần lỗi không làm dừng cả script: các dòng của phần đó ghi `LỖI` kèm thông điệp. `--skip` ghi `bỏ qua`.
- JSON ghi đè `backend/eval/reports/pitch_numbers.json` (thư mục `reports/` không commit).

## Q3. Runbook

- Viết theo API + `web/` hiện có; chỗ cần giao diện chưa có ghi "[UI?]". Phần phát lại/nhảy giờ/cảnh báo ghi "Chờ M4: lệnh sẽ cập nhật", không bịa lệnh.
- Dựng DB pitch bằng `app.demo_import --models`, chạy server bằng `scripts/dev.mjs --db …` (vì `demo_import --serve` tắt AI).
- Bản ghi AI hiện là FakeClient: runbook cấm nói "AI đã chạy OpenAI thật" cho tới khi đội ghi lại bằng key thật.

## Q4. Một lệnh chuẩn bị demo: `scripts/demo.mjs`

- Các bước: dựng DB → bật backend → mục tiêu profit CD002 (lead-1, nếu chưa có) → làm nóng So sánh CD002 (`POST /scenarios/run`) → bật web → in tóm tắt. Cờ: `--db` (dùng DB có sẵn, bỏ bước dựng), `--out`, `--models`, `--skip-goal`, `--skip-warm`, `--no-web`, `--api-port`, `--web-port`. Lệnh con khi đang demo: `jump <H>`, `home` (reset + jump 0 = về 01:00), `replay [từ] [giây]`, `stop`, `status`.
- Biến môi trường chỉ truyền cho tiến trình con (`APP_ENV=demo`, `DUCKDB_PATH`, `DATA_DIR`, `LIVE_DIR=<thư mục DB>/live_stream`, `LIVE_ENABLED=true`, `DEMO_MODE=true`, `AI_ENABLED=true`, `AI_MODE=replay`, `CORS_ORIGINS`). `backend/.env` không bị đọc/sửa bởi script; script không in biến nào chứa key. Uvicorn chạy không `--reload` (ổn định khi demo).
- Hàm spawn/log/tắt cây tiến trình tách ra `scripts/lib/proc.mjs`. `scripts/dev.mjs` **giữ nguyên** (không đụng launcher đang dùng).
- **DB demo dựng qua đúng đường phát lại, không backtest/fit.** Lệnh: `app.demo_import --replay-hour 0 --estimate-ads` (cờ mới). 11.11 được ghi vào `<out>/live_stream` bằng `app.live.replay.write_live_stream(…, 0)` rồi nạp từ đó; server dùng chính thư mục này làm `LIVE_DIR`, nên `jump` nối tiếp cùng con trỏ, và `home` cho lại **đúng** trạng thái đầu. Lý do (đo trên `demo`, 30/10):

  | DB 01:00 | CD002 hơn chạy tiếp | [4g] chỉ tiêu 97 | flip explain | replay `whatif` | replay `explain` |
  |---|---|---|---|---|---|
  | `demo_import --until … --models` (runbook cũ) | 3,97 tr | **none_meets_goal** (30%: 67%, khung giờ 51%) | −199.448đ | "đạt" nhưng **sai số** (xem dưới) | gave_up → 503 |
  | `demo_import --until …` + estimate-ads | 3,99 tr | reduce 30% (81% / 57%) | −251.137đ (lệch 0,51%) | đúng | gave_up (vượt dung sai 0,5%) |
  | `--replay-hour 0 --estimate-ads` (mới) | 3,99 tr | reduce 30% (81% / 57%) | −252.425đ = bản ghi | đúng | đúng |

  Số pitch (`eval.pitch_numbers`, `eval.demo_whatif`) và 3 bản ghi AI đều đo trên DB **không** backtest/fit, đi đường phát lại. Có backtest/fit thì cảnh what-if "97 cái" (K4, không được bỏ) ra "không phương án nào đạt". Nên **không bản ghi nào phải ghi lại**; chỉ đổi cách dựng DB. `--models` vẫn còn để thử, script in cảnh báo.
- Hệ quả: lúc 01:00 Ads trễ 240 phút (huy hiệu "cũ hơn ngưỡng"), như đường phát lại ở Q1. Đúng với yêu cầu "giữ nguyên dữ liệu"; câu nói trong runbook.

## Q5. Bug tìm thấy khi diễn tập

- **`POST /scenarios/run` 500 "Conflict on update"** khi chạy lúc orchestrator đang tính lại (đặt mục tiêu CD002 phát `GoalChanged`, ngay sau đó demo.mjs làm nóng So sánh). Cả hai ghi `forecasts`/`demand_groups`; orchestrator giữ khóa ghi live, API chỉ giữ `_RUN_LOCK`. Sửa: `/scenarios/run` lấy khóa ghi live của runtime **trước** `_RUN_LOCK` (cùng thứ tự với `Orchestrator._simulate`, không deadlock). Test `tests/api/test_scenarios.py::test_run_waits_for_the_live_write_lock`. Kết quả mô phỏng không đổi (`eval.demo_whatif --only 1,4g,5,8a` trước/sau như nhau).
- **Chưa sửa, báo chủ lớp AI:** công cụ AI (`compare_actions`, `run_scenario`) cũng ghi mà không lấy khóa ghi live; hỏi AI đúng lúc tick đang tính có thể gặp cùng lỗi. Demo tránh được vì `jump … wait=true` chờ tính xong.
- **Chưa sửa, báo chủ lớp AI (grounding dương tính giả):** trên DB có backtest/fit, bản ghi `whatif` vẫn ra "kiểm số 8/8" dù công cụ trả 67%/51%: "81%" khớp kiểu "phép tính một bước 0.5 + 80", "57%" khớp một con số trong `recommendation.reasons`. Với DB demo mới số khớp thật (81%/57% có trong `p_target`), nhưng luật khớp phép tính cho `%` quá rộng.

## Q6. Diễn tập tự động: `eval.rehearsal`

- Chạy đúng thứ tự cảnh a–g qua API (HTTP với `--base-url`, hoặc TestClient trong process trên bản sao `--db`, hoặc tự dựng DB như demo.mjs). Mỗi lượt kết thúc bằng `reset` + `jump 0`; lượt 2 chạy trên trạng thái sau reset. Ghi `eval/reports/rehearsal.json`.
- Mốc kiểm: data_as_of 01:00; CD002 `schedule_hours:0-2,12-14`, hơn chạy tiếp 3,99 ± 0,1 tr, pause/pause_until_restock không khả thi, có ZoneBar, đề xuất hiện hành cũng là khung giờ; AI: `outcome=answered`, `replayed`, grounding ok, có nguồn, chữ bắt buộc ("giảm ngân sách 30%", "81%", "AOGIUNHIET-M", "hết hàng"); quyết định draft → pending → approved (lead-1), lead-2 tự duyệt → 403 `self_approval`; jump 10 → `sales_above_forecast` BINHNUOC500; jump 13 → `stockout_risk` AOGIUNHIET-M `:out` có nhắc CD005.
- `AI_RECORD_DB=<demo.duckdb>` (fixture `demo_ai_dbs`) cho phép ghi lại bản ghi FakeClient trên đúng DB demo nếu sau này đổi cách dựng DB. Lần này **không** dùng để ghi đè bản ghi.

## Q7. Fixtures từ API thật

Trang công khai (`web/` build `VITE_USE_FIXTURES=true`) trước đây dùng số soạn tay (5 SKU, nồi chiên tồn 41, hơn chạy tiếp 4,3 tr, "dữ liệu tới 14:59"), lệch với pitch. Đổi sang **ảnh chụp API thật lúc 01:00 ngày 11.11**.

- Script `backend/eval/record_fixtures.py` (`uv run python -m eval.record_fixtures --out ../web/src/api/fixtures [--db PATH]`): dựng DB tạm bằng `app.demo_import --until 2026-11-11T01:00:00+07:00 --models` (như runbook 1.1; ~3 phút), lead-1 đặt mục tiêu profit CD002, chạy `POST /scenarios/run` đúng như nút đầu tiên trên màn So sánh (1.000 mẫu, seed 20261111), rồi ghi các GET mà web gọi qua TestClient: `/health`, `/me`, `/freshness`, `/live/status`, `/alerts?status=open`, `/recommendations?active=true`, `/recommendations/{id}`, `/scenarios/{id}`, `/campaigns/CD002`, `/skus/NOICHIEN2L`, `/skus?sort=priority`. Giữ nguyên `{data, meta}`. DB tạm xóa khi xong; không đọc `ground_truth`.
- **Tên file theo id thật**: router fixture (`web/src/api/client.ts`) đổi từ bảng id cứng (`rec-551`, `scn-2291`) sang quy ước `/recommendations/{id}` → `recommendation-{id}.json` (tương tự `scenario-`, `campaign-`, `sku-`). Ghi lại fixtures thì id đổi, không cần sửa code. Test tra id qua `/recommendations` thay vì viết cứng.
- **Danh sách SKU**: giữ 50 dòng ưu tiên cao nhất (43 KB), `meta.total = 300` thật, `next_cursor = null` (fixture không phân trang). Bảng ghi "Toàn bộ SKU (300)" và "Đã tải 50/300 mã" (sửa `loadedCount`: có `total > n` thì ghi n/total kể cả khi hết trang).
- **Giờ máy → 01:00**: `computed_at`, `received_at`, `created_at`… lúc ghi là giờ máy (30/10). Đổi thành 01:00 11/11 (chỉ chuỗi có phần lẻ giây và không muộn hơn lúc ghi; mốc dữ liệu mô phỏng giữ nguyên), để màn hình ghi "Dữ liệu tới 01:00 · tính lúc 01:00". `live_dir` (đường dẫn máy) bỏ khỏi `live-status.json`.
- **PII**: script quét sđt, email và mọi chuỗi tên/sđt/địa chỉ/ghi chú người mua lấy từ file đơn hàng; thấy là thoát mã 1. Lần ghi này: 0.
- **Số thật hiện trên web** (khớp `eval.pitch_numbers`): CD002 `schedule_hours` 0–2h, 12–14h, hơn giảm 50% **1.226.007đ** ("khoảng 1,2 triệu"), hơn chạy tiếp ~3,97 tr, p = 1,00; pause và pause_until_restock "Không làm được" (`campaign_must_run`); ZoneBar `pause_better` (ngưỡng 0, khoảng 3,8–5,3 sp/giờ) kèm ghi chú "bị cấm". Nồi chiên tồn **76**, hết khoảng 16:00 (theo dự báo; lý do của đề xuất ghi 14:00 khi chạy tiếp). Cảnh báo lúc 01:00 chỉ có **1** (thiếu giá vốn 27 SKU) — chấp nhận số thật. Lật kết luận duy nhất: hàng dư ≤ −199.448đ/sp (không có điều kiện "hàng về" như fixture cũ, nên chế độ fixtures chỉ hiện thanh trượt hàng dư).
- Giữ ví dụ minh họa soạn tay `rec-540`/`scn-2280` (CD002 ngày thường) và `rec-510`/`scn-2210` (ví dụ trang 10); màn So sánh ghi "Số liệu minh họa soạn tay" cho hai ca này, còn ca thật ghi "Ảnh chụp kết quả mô phỏng lúc 01:00 11.11". Nhãn "Dữ liệu mẫu" trên thanh trên giữ nguyên, tooltip nói rõ là ảnh chụp lúc 01:00.
