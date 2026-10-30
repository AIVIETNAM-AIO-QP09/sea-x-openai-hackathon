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
