# M3 · Quyết định phần web (WEB-02, WEB-05)

Ghi các quyết định tự đưa ra khi làm thành phần dùng chung, ZoneBar và màn So sánh lựa chọn. Mỗi mục: vấn đề, lựa chọn, lý do, ảnh hưởng. Mục 10 liệt kê những gì web cần từ API ở đợt sau.

## 1. `breakeven.ts` dùng chung công thức với backend (ECO-04)

- **Vấn đề:** 09 §2.3 cần kéo thanh trượt là ZoneBar đổi ngay (< 100 ms), không chờ mô phỏng. 12 (ECO-04) yêu cầu frontend và backend dùng chung một công thức.
- **Lựa chọn:** `web/src/lib/breakeven.ts` là bản TypeScript thuần của 05 §7.1. Đầu vào đúng tên trường của body `POST /scenarios/breakeven` (08 §3.8), đầu ra đúng `{zone_bar, flip_leftover_value_vnd}`. `continue` bán đều `rate_continue_per_hour` và chi `spend_per_hour_vnd` tới khi hết hàng hoặc hết giờ, nên `Π_c(V) = m·sold − spend + V·(n − sold)`. Điểm đổi `V*` tính tại p10 (từ giá trị này trở lên thì pause tốt hơn trên cả khoảng dự báo), dùng công thức tổng quát `V* = (P0 − m·q)/(n − q − L_c)`.
- **Ca biên:** `m ≤ V` → `zone_bar = null`; `q* ≤ 0` → ngưỡng 0, `pause_better`; `q* > n` → ngưỡng `n/H`, `continue_better`. Có test cho cả ba. Với chi ads ≥ 0 và m > V thì `q* ≤ n` luôn đúng, nên ca `q* > n` chỉ xảy ra khi chi âm (vd sàn trợ giá ads); vẫn giữ để khớp 05.
- **Test bắt buộc (vitest, xanh):** n=120, H=4, m=45.000, Π_c=4.050.000 → x* = 22,5 (V=0), 16,5 (V=20.000); V* = 16.875đ khi p10 = 18.
- **Ảnh hưởng:** backend ECO-04 nên chạy cùng bộ số. Nếu `breakeven.py` chọn khác (vd V* tại p90), sửa một hàm ở web.

## 2. Đề xuất thêm `ZoneBar.inputs` (tùy chọn)

- **Vấn đề:** `Recommendation` ở 05/08 không mang n, H, m, Π_c, nên trình duyệt không tự tính lại thanh vùng được.
- **Lựa chọn:** thêm trường tùy chọn `zone_bar.inputs: BreakevenRequest | null` (08 §1: thêm trường không phá vỡ). Có `inputs` thì kéo "giá trị hàng dư" vẽ lại ZoneBar ngay bằng `breakeven.ts`, ghi "Ước tính nhanh trên trình duyệt (công thức hòa vốn), chưa chạy lại mô phỏng". Không có thì chỉ chờ server.
- **Ca CD002 11.11 không có `inputs`:** thanh vùng của 08 (ngưỡng 3,1; khoảng 4,2–7,0) là số minh họa. Với Π_c = −4,48 triệu thì công thức đóng cho q* < 0 (pause thắng chắc), không ra 3,1. Bịa `inputs` cho khớp 3,1 là không trung thực, nên fixture CD002 không có `inputs`. Ở chế độ fixture, thanh "hàng dư" của ca này bị ẩn, chỉ còn thanh "hàng về sớm/trễ" (ước tính theo `flip_conditions`).

## 3. Ba ca fixture cho màn So sánh (minh họa)

| Ca | Đường dẫn | Kết luận | Mục đích |
|---|---|---|---|
| CD002 11.11 (`rec-551`, `scn-2291`) | `/sku/NOICHIEN2L/compare`, `/campaign/CD002/compare` | `schedule_hours` thắng; `pause` và `pause_until_restock` `feasible=false` vì `campaign_must_run` | Ca chính 05 §10, số đúng 08 §3.8 |
| CD002 ngày thường 05/11 (`rec-540`, `scn-2280`) | `/campaign/CD002/compare?rec=rec-540` | `continue` thắng, thanh vùng `continue_better` (ngưỡng 3,49; khoảng 1,8–3,1) | Cặp "cùng chiến dịch, kết luận ngược" của 05 §10 |
| Ví dụ trang 10 (`rec-510`, `scn-2210`, chiến dịch giả `VIDU-T10`) | `/campaign/VIDU-T10/compare?rec=rec-510` | `undetermined`, ngưỡng 22,5 với khoảng 18–31; kéo hàng dư lên 20.000đ → 16,5 → `pause_better` | Yêu cầu 09 §2.3 "màn này phải chạy đúng ví dụ trang 10" |

- Ca ngày thường và ca trang 10 có `zone_bar.inputs` khớp đúng `breakeven.ts` (test kiểm 3,4946 và 3,339).
- Mỗi file fixture mới có trường `_note` ghi rõ là minh họa. App bỏ qua trường này.
- Tham số `?rec=<id>` trên route `/campaign/:id/compare` để mở một đề xuất cụ thể (kể cả đề xuất cũ). Không có `?rec` thì lấy đề xuất đang hiệu lực của chiến dịch từ `GET /recommendations`.
- `/compare` (không tham số) thành trang chọn: danh sách đề xuất đang hiệu lực, và ở chế độ fixture thêm ba ca minh họa.

## 4. `ActionSpec.pct` là tỷ lệ

- **Vấn đề:** 05 §1 ghi `pct: 0.3 = giảm 30%`; fixture M0 ghi `30` và `50`.
- **Lựa chọn:** theo 05: fixture đổi về `0.3`, `0.5`. Hàm `pctOf` trong `i18n.ts` đọc `≤ 1` là tỷ lệ, `> 1` là phần trăm để không vỡ nếu backend gửi kiểu cũ.

## 5. Kiểu nullable theo 05

`Recommendation.best`, `p_best_beats_runner_up`, `expected_gain_vnd`, `zone_bar` đổi thành `| null` đúng 05 §1 (ca `none_meets_goal`). Tổng quan ca và test đã sửa theo. Thêm alias trong `types.ts`: `ZoneVerdict`, `AltThreshold`, `BreakevenRequest`, `BreakevenResponse`, `FlipCondition`, `InputsRef`, `SimRequest`, `DecisionCreate`, `DecisionCreated`.

## 6. Lý do có số dạng CitationChip

- **Vấn đề:** `reasons` ở 05/08 là chuỗi trần, không biết mỗi lý do lấy từ nguồn nào.
- **Lựa chọn:** đề xuất trường tùy chọn `reason_sources: (Source | null)[]` cùng thứ tự `reasons`; `Source` thêm tùy chọn `data_as_of`, `tool`, `href`. Thiếu thì chip trỏ về mô phỏng của đề xuất. Con số chính trong câu (ưu tiên số có đơn vị hoặc giờ: "9.280đ", "13:00", "18–31 sp/giờ", không lấy "11.11") là nút mở popover nguồn.

## 7. Thanh trượt và gọi lại mô phỏng

- Chế độ API thật: kéo → `POST /scenarios/run` với `param_overrides` (`leftover_value_per_unit`, `restock_delay_days`, đúng khóa 05 §3), `samples=300`, debounce 250 ms; thả tay (pointerup/keyup/blur) → `samples=1000`. Kết quả cũ chỉ được dùng nếu khớp giả định hiện tại; trong lúc chờ, tầng 1 mờ 60% kèm "Đang cập nhật · dữ liệu lúc …".
- Chế độ fixture: không gọi mạng, chỉ ước tính bằng `breakeven.ts` và so với `flip_conditions` ("Với giả định này đã chạm điểm đổi: …"). Ghi rõ là ước tính nhanh.
- Thanh "hàng về trễ" cho phép −3 tới 7 ngày (số âm = về sớm), vì ví dụ 08 có `flip_at: -1` trong khi 05 §3 ghi khoảng 0–7. Backend cần nhận giá trị âm, hoặc báo lại để web giới hạn từ 0.
- Thanh "giá trị hàng dư" có max = m (đóng góp mỗi sp) khi có `inputs`, vì từ m trở lên công thức không còn thanh vùng (hiện câu "Giữ hàng lợi hơn bán…"). Không có `inputs` thì max tạm 1.000.000đ; đúng ra là giá bán (05 §3), cần API trả.
- `SimRequest` khi gọi lại: dùng `ScenarioRun.request` nếu API trả (đề xuất thêm), nếu không thì dựng từ `inputs_ref` (`start` = giờ tròn kế tiếp sau `data_as_of`, `horizon_hours = null` để backend lấy mặc định theo goal).

## 8. Form "Tạo quyết định"

Form tối giản: chọn hành động (hành động vi phạm ràng buộc hiện nhưng không chọn được), lý do (điền sẵn từ `reasons`), báo "Khác với đề xuất" khi ghi đè, báo "đang dùng giả định" khi thanh trượt đã đổi. Nút "Lưu bản nháp quyết định" gọi `POST /decisions` có `Idempotency-Key`, sau đó "Gửi duyệt" gọi `/decisions/{id}/submit`. Nút bị khóa kèm lý do hiện ngay dưới: chế độ dữ liệu mẫu, vai trò Xem, hành động vi phạm, thiếu lý do. Nút "Báo lead" của ca `none_meets_goal` khóa kèm lý do (chưa có API).

## 9. Thành phần dùng chung (WEB-02)

- `ConfidenceBadge`, `ComputeStateTag` giữ từ M0. `FreshnessBadge` thêm tooltip "trễ 2 giờ 4 phút (ngưỡng 3 giờ)", "thiếu 17 mã" theo 09 §4.
- Mới: `CitationChip` (popover: loại nguồn, mã, công cụ, dữ liệu tới, tính lúc, link; Esc / bấm ngoài để đóng), `MoneyVND` (đủ / `tr` / `triệu`), `Range` (`(−4,9 … −4,1)`, có `aria-label`), `Banner` (vàng: dữ liệu cũ; xám: kịch bản), `UpdatingRegion` (mờ 60% + "Đang cập nhật · dữ liệu lúc 13:05"), `ZoneBar`.
- `ZoneBar` là SVG tự vẽ, không thêm thư viện. Màu vùng là hai token mới `--zone-continue` / `--zone-pause` (xanh nhạt / vàng nhạt, có bản tối), không mang nghĩa tốt/xấu. Ngưỡng chính vạch liền, ngưỡng phụ vạch đứt, khoảng p10–p90 là thanh dày, p50 là chấm rỗng viền đậm. `role="img"` + `aria-label` đọc đủ câu kết luận, ba con số và các ngưỡng phụ. Câu kết luận và số cũng in dưới thanh dạng chữ.
- Hàm phụ của ZoneBar nằm ở `lib/zoneBarText.ts` để file component chỉ export component (luật react-refresh).
- Không thêm gói npm nào.

## 10. Cần API ở đợt sau

| Endpoint | Trường / hành vi | Dùng cho |
|---|---|---|
| `GET /recommendations/{id}`, `POST /scenarios/run` | `zone_bar.inputs` (= body `POST /scenarios/breakeven`) | Vẽ lại ZoneBar ngay khi kéo |
| `GET /recommendations/{id}` | `reason_sources[]` cùng thứ tự `reasons`; `Source.data_as_of`, `tool`, `href` | CitationChip cho từng lý do |
| `GET /scenarios/{id}`, `POST /scenarios/run` | `request` (SimRequest đã chạy, gồm `samples`, `seed`, `horizon_hours`) | Gọi lại đúng tham số; tầng 3 |
| `POST /scenarios/run` | Nhận `restock_delay_days` âm (hàng về sớm), `meta.compute_state`, `meta.cache_hit` | Thanh trượt; trạng thái đang tính |
| `GET /recommendations?campaign_id=` | Lọc theo chiến dịch | `/campaign/:id/compare` khỏi tải cả danh sách |
| `GET /skus/{sku}` hoặc `GET /campaigns/{id}` | Tên chiến dịch, danh sách SKU, giá bán (max của thanh hàng dư) | Tiêu đề màn và giới hạn thanh trượt |
| `GET /goals` | Nhãn mục tiêu theo `goal_id` | "Mục tiêu: Lợi nhuận trong ngày 11.11" thay cho mã |
| `POST /decisions`, `/decisions/{id}/submit` | Như 08 §3.10 | Bật nút Lưu bản nháp / Gửi duyệt |
| `ScenarioResult` | `leftover_units`, `spend`, `units_sold` đủ cho mọi hành động khả thi | Bảng tầng 3 (hiện "—" khi thiếu) |
