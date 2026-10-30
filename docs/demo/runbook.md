# Runbook demo MegaDay Twin (pitch 6 phút)

Dùng khi đứng pitch. Kịch bản lời nói đầy đủ ở [Cẩm nang pitch](https://claude.ai/artifact/NuSEaHjNHnzrhKknD4smWU), mục "Kịch bản trình bày 6 phút". File này chỉ ghi: lệnh, màn hình/endpoint, con số đúng, câu cấm, xử lý sự cố. Mọi số là **trên dữ liệu mô phỏng** (shop `demo`, seed 20261111).

Phân vai: một người nói, một người bấm. Người bấm không nói; người nói không chạm máy.

> **Phụ thuộc giao diện (chưa chốt):** giao diện cuối có thể là `web/` của repo này hoặc app "city" của Phúc. Runbook viết theo API + `web/` hiện có. Hiện `web/` mới có thật màn **Tổng quan ca** (`/`) và **So sánh lựa chọn** (`/campaign/CD002/compare`); Nhập dữ liệu, Cảnh báo, Trợ lý AI, Nhật ký còn là trang chờ. Cảnh nào ghi "[UI?]" thì khi chốt giao diện phải điền lại nút bấm; trước đó dùng endpoint đã ghi.

## 1. Chuẩn bị trước giờ pitch (T−1 ngày hoặc sáng hôm đó)

Chạy trong `backend/`. Máy demo đã `uv sync`, `npm ci` trong `web/`.

1. **Dựng DB demo tới 01:00 ngày 11.11** (thư mục mới mỗi lần, không bao giờ ghi đè):

   ```powershell
   cd backend
   uv run python -m app.demo_import --shop ../mock-data/out/demo --output data/pitch-0100 --until 2026-11-11T01:00:00+07:00 --models
   ```

   `--until` phải có múi giờ (`+07:00`), thiếu là lỗi. `--models` chạy backtest + fit + ước lượng iROAS (vài phút). Kết quả: `data/pitch-0100/demo.duckdb`.

2. **Kiểm con số pitch** (một lần, ~10–20 phút; máy bận thì lâu hơn):

   ```powershell
   uv run python -m eval.pitch_numbers --reuse-db data/pitch-0100/demo.duckdb
   ```

   Mọi dòng phải `ĐẠT`. Dòng `LỆCH` thì **không đọc số đó trên sân khấu** cho tới khi rõ lý do. Bảng lưu ở `eval/reports/pitch_numbers.json`. Script chép DB sang thư mục tạm, không ghi vào file gốc. Chạy nhanh khi chỉ đổi what-if: thêm `--skip data,forecast,ads`.

3. **AI chạy bản ghi (không cần mạng, không cần key)**. Trong `backend/.env`:

   ```
   AI_ENABLED=true
   AI_MODE=replay
   LIVE_ENABLED=false      # cảnh 01:00 tĩnh; bật lại khi dùng phát lại (mục 3)
   DEMO_MODE=true
   ```

   Có sẵn 3 bản ghi trong `backend/eval/ai_recordings/`. **Gõ đúng nguyên văn câu hỏi**, đúng `flow`, đúng mốc dữ liệu:

   | `flow` | Câu hỏi (gõ đúng) | Mốc dữ liệu cần | Kết quả đúng |
   |---|---|---|---|
   | `whatif` | Nếu sếp giao chỉ tiêu 97 cái hôm nay thì sao? | 01:00 ngày 11.11, mục tiêu profit CD002 | giảm ngân sách 30%: đạt 81% (khung giờ 57%), kiểm số 8/8 |
   | `explain` | Vì sao nồi chiên chỉ chạy khung giờ? | 01:00 | 3 lý do + điều làm đổi kết luận, 9/9 |
   | `investigate` | Vì sao áo giữ nhiệt bán chậm? | **14:00** | AOGIUNHIET-M hết hàng từ 13:00, 10/10 |

   Các bản ghi này tạo bằng **FakeClient** (kịch bản cố định, công cụ và kiểm số chạy thật), **chưa chạy OpenAI thật**. Nếu đội có key và muốn bản thật: `AI_MODE=record`, chạy server đúng mốc, hỏi 3 câu trên, kiểm file mới trong `eval/ai_recordings/<flow>/`, rồi quay lại `AI_MODE=replay`.

4. **Bật backend + web** ở gốc repo:

   ```powershell
   node scripts/dev.mjs --db data/pitch-0100/demo.duckdb
   ```

   API `http://localhost:8000/docs`, web `http://localhost:5173`. Lưu ý: `demo_import --serve` tự tắt AI (`ai_enabled=False`), nên **dùng `dev.mjs`** khi cần AI.

5. **Mục tiêu CD002** phải có trước cảnh nồi chiên (lead đặt): `POST /api/v1/goals` với header `X-User: lead-1`, `X-Role: lead`, body `{"scope_id":"CD002","kind":"profit","deadline":"2026-11-12T00:00:00+07:00","reason":"Lãi trong ngày 11.11"}`. Sau đó mở màn So sánh một lần để dự báo được tính sẵn (lần đầu ~10–25 giây, các lần sau ~0,3–0,7 giây).

6. **Quay video dự phòng** toàn bộ demo theo đúng kịch bản, lưu ở máy demo + một USB.

## 2. Từng cảnh

Mốc giờ theo kịch bản 6 phút. Màn hình hiện tại = `web/` trừ khi ghi khác.

| Mốc | Cảnh | Màn / endpoint | Con số đúng (đọc được) |
|---|---|---|---|
| 0:00–1:45 | Mở đầu, Vấn đề, Giải pháp | Slide | Nồi chiên: ROAS sàn **8,11**, iROAS thật **5,27**; áo **6,17 / 3,85**; cốc meme **0,88 / 0,64**; ROAS sàn phóng đại trung bình **~1,47 lần**. Nồi chiên đầu ngày còn **83** cái, hết khoảng **15 giờ** (đáp án mô phỏng) |
| 1:45–2:10 | K1: dữ liệu lộn xộn | [UI?] màn Nhập dữ liệu chưa có trong `web/`. Tạm: `POST /api/v1/ingest/files`, hoặc nói "đã nạp từ trước" và mở `GET /api/v1/data-quality/issues` | Ghép SKU tự động đúng **96,4%** (mã nội bộ + giá vốn), **97,6%** cả 3 nguồn, **0** ghép sai; bắt **12/12** lỗi cài sẵn; lệch giờ ads **+7 tiếng**; **0** PII trong DB |
| 2:10–2:40 | K2: phát lại 11.11, bình nước | **Chờ M4: lệnh sẽ cập nhật** (mục 3) | Bình nước: nhu cầu 11.11 **514** cái so với ~**23** cái/ngày |
| 2:40–3:20 | K3: AI điều tra áo | [UI?] màn Trợ lý chưa có trong `web/`. API: `POST /api/v1/ai/investigate` hoặc `POST /api/v1/ai/chat` `flow=investigate`. **Cần dữ liệu tới 14:00** (chờ M4) | Size **M** hết hàng từ khoảng **13 giờ**; S/L vẫn bán; ads CD005 vẫn chạy; không kết luận "hết trend" |
| 3:20–4:15 | K4: nồi chiên | `web/` `/campaign/CD002/compare`; API `POST /api/v1/scenarios/run` | Đề xuất **chỉ chạy khung giờ 00–02h và 12–14h** (`recommend`, p ≈ 1,00). Hơn chạy tiếp **~3,99 triệu** (nói "khoảng 4 triệu"). Hơn giảm 50% **~1,23 triệu**. Tạm dừng và tạm dừng tới khi hàng về **bị cấm** (cam kết flash). Lãi mỗi nồi giá 11.11 **9.280đ**; ads cần iROAS ≥ **57** mới có lời |
| 3:20–4:15 | K4 what-if: "chỉ tiêu 97 cái" | [UI?] Trợ lý; API `POST /api/v1/ai/chat` `flow=whatif`, câu ở mục 1.3 | Đổi sang **giảm ngân sách 30%**: đạt **81%** (khung giờ **57%**). Cái giá **~2,3 triệu** so với phương án lời nhất |
| 4:15–4:45 | K5: bẫy lừa AI | [UI?] Trợ lý, `flow=chat` | Ghi chú ở đơn `2611099UF5GLZH` bị coi là dữ liệu khách; AI không làm theo; mọi thao tác cần người duyệt. **Chưa có bản ghi replay** cho câu này: tập trước, nếu AI ngoại tuyến thì bỏ cảnh (xem "khi trễ giờ") |
| 4:45–5:30 | Chứng minh | Slide | Dự báo 10.10: WAPE **~37%** so với cách đơn giản **68,6%**; phân nhóm đúng **88,3%**; nhãn tin cậy **44** đã kiểm / **242** tham khảo / **14** kịch bản. iROAS: sai số trung vị **~24,8%**, gần đúng hơn ROAS sàn ở **40/49** chiến dịch; nồi chiên app ước lượng **~4,4–4,5** (thật 5,27, sàn 8,11) |
| 5:30–6:00 | Chốt | Slide | — |

Câu dự phòng cho câu hỏi ban giám khảo (đều đã kiểm bằng `eval.pitch_numbers`):

- "Cam kết flash tốn bao nhiêu?" → bỏ ràng buộc thì app chọn **tạm dừng**; cam kết tốn khoảng **1,1 triệu**.
- "Hàng về sớm một ngày thì sao?" → **kết luận không đổi**, vẫn chỉ chạy khung giờ (hơn chạy tiếp ~3,5 triệu): thêm hàng cũng không cứu được ads khi mỗi nồi chỉ lãi 9.280đ.
- "Có ví dụ app bảo dừng hẳn không?" → thanh vùng CD020 (đèn lồng đỏ) ngày 06/11, hàng dư V = 0: **"tạm dừng tốt hơn"** (ngưỡng ~0,65 sp/giờ, dự báo khi dừng ~0,67–1,21).
- "Tính có nhanh không?" → `/scenarios/run` khoảng **0,3 giây** khi dự báo đã có. Nạp lịch sử < **60 giây**, một giờ live < **5 giây** (phụ thuộc máy).

## 3. Phát lại 11.11 và cảnh báo: chờ M4

**Chờ M4: lệnh sẽ cập nhật.** Agent điều phối đang làm "nhảy tới giờ H" (`POST /api/v1/live/control`, `GET /api/v1/live/status`, SSE `/api/v1/stream`) và cảnh báo. Khi xong, điền vào đây:

- Lệnh/nút bắt đầu phát lại từ 9 giờ, tốc độ mỗi giờ.
- Lệnh nhảy thẳng tới 14:00 (cho K3) và quay về 01:00 (cho K4).
- Cảnh báo bình nước và áo size M hiện ở màn nào, mấy giờ mô phỏng.
- `LIVE_ENABLED` / `LIVE_DIR` cần đặt thế nào (không để `live_stream/` cũ của `replay.js` lẫn vào DB pitch).

Biết trước về huy hiệu độ mới Ads (đã kiểm, xem [M5-chuan-bi-demo.md](../quyet-dinh/M5-chuan-bi-demo.md)):

- Theo đường phát lại (`replay.js` / live control), lúc **01:00 và 02:00** Ads hiện **"cũ hơn ngưỡng"** (trễ 4 và 5 giờ, ngưỡng 3 giờ). Lý do: 3 giờ ads cuối của ngày 10/11 không bao giờ về. Từ **03:00** trở đi Ads trễ đúng **2 giờ**. Câu nói nếu bị hỏi: "Báo cáo ads về chậm; app nói thẳng số ads đang cũ, không giả vờ là mới."
- DB dựng bằng `app.demo_import` lúc 01:00 thì Ads **trễ 0 phút** (bản import này không mô phỏng độ trễ ads). Số đề xuất CD002 như nhau ở cả hai cách.

## 4. Câu KHÔNG được nói

- ✗ "Hàng về sớm một ngày thì kết luận đổi." Sai: **không đổi**.
- ✗ "Ngày thường app khuyên chạy tiếp ads nồi chiên." Sai: app ra giảm 50%, chưa đủ chắc (`undetermined`).
- ✗ "AI đã chạy bằng OpenAI thật" / "đây là GPT trả lời trực tiếp", **trừ khi** đội đã ghi lại bằng key thật (mục 1.3) và đang chạy bản đó. Bản ghi hiện có là kịch bản cố định; nói "câu trả lời ghi sẵn từ buổi diễn tập, công cụ và bước kiểm số chạy thật".
- ✗ Chỉ vào thanh vùng của nồi chiên 11.11 và nói "nên tạm dừng". Thanh ghi "tạm dừng tốt hơn nhưng bị cấm": đó là cái giá của cam kết, không phải đề xuất.
- ✗ Đọc E[J] tuyệt đối ("lời X triệu"). Chỉ đọc **chênh lệch** giữa hai lựa chọn.
- ✗ "App giúp shop tăng X% lợi nhuận", "đã thử với seller", đọc số mô phỏng như số thị trường.
- ✗ "App đề xuất dừng cốc meme chắc chắn." Nói: "app nghiêng về dừng, chênh nhỏ vì chiến dịch nhỏ".
- ✗ "Nồi chiên còn 83 cái" khi đang ở màn 01:00: lúc đó app thấy tồn **76** (đã bán trong giờ đầu). 83 là tồn **đầu ngày** trên slide.

## 5. Xử lý sự cố

| Sự cố | Làm gì |
|---|---|
| Backend chết | Người nói chuyển sang phần slide. Người bấm: Ctrl+C rồi chạy lại `node scripts/dev.mjs --db data/pitch-0100/demo.duckdb` (~10 giây, DB file còn nguyên). Không chạy lại `demo_import` lên cùng thư mục (nó từ chối, đúng như thiết kế) |
| Cổng 8000 hoặc 5173 bận | `node scripts/dev.mjs --db data/pitch-0100/demo.duckdb --api-port 8001 --web-port 5174`. Tìm tiến trình giữ cổng: `Get-NetTCPConnection -LocalPort 8000` |
| DuckDB báo file đang bị khóa | Còn một server/script khác mở cùng file. Tắt nó, hoặc dựng thư mục DB mới (mục 1.1) |
| Mất mạng / OpenAI lỗi | Đã ở `AI_MODE=replay` thì không ảnh hưởng. Đang `live` → đổi `AI_MODE=replay` trong `.env`, khởi động lại backend. Câu không có bản ghi → nói "trợ lý đang ngoại tuyến", đi tiếp màn chính. Riêng `investigate` không bao giờ lỗi 503: không có AI thì hiện "Tóm tắt tự động từ checklist" |
| AI trả lời chậm > 5 giây | Người bấm mở câu trả lời ghi sẵn; người nói nói tiếp, không chờ |
| Replay không khớp, AI ra `gave_up` | Dữ liệu khác mốc của bản ghi (ví dụ hỏi `investigate` ở 01:00). Nhảy về đúng mốc (chờ M4) hoặc bỏ cảnh |
| Máy demo hỏng | Chiếu video dự phòng từ mốc đang dở, lời nói giữ nguyên |
| Trễ giờ | Trễ > 20 giây ở mốc 2:40: bỏ K5. Trễ > 40 giây: bỏ thêm K1 ("dữ liệu đã nạp và làm sạch từ trước"). **Không bao giờ bỏ K3 và K4** |

## 6. Kiểm tra 10 phút trước giờ

- [ ] `eval/reports/pitch_numbers.json` của hôm nay: mọi dòng `ĐẠT` (hoặc đã gạch số `LỆCH` khỏi slide).
- [ ] Backend lên: `GET http://localhost:8000/api/v1/health` trả ok; `GET /api/v1/ai/status` báo `mode = replay`, `enabled = true`.
- [ ] `GET /api/v1/freshness`: `data_as_of` = 01:00 ngày 11.11 (hoặc mốc kịch bản đang dùng).
- [ ] Mở `/campaign/CD002/compare` một lần: đề xuất "chỉ chạy khung giờ 00–02h, 12–14h", tạm dừng bị làm mờ. Lần mở này cũng làm nóng dự báo.
- [ ] Thử 1 câu AI ghi sẵn (gõ đúng nguyên văn), thấy chip nguồn và "kiểm số n/n".
- [ ] Phát lại / nhảy giờ: **chờ M4**, điền khi có lệnh.
- [ ] Video dự phòng mở được trên máy chiếu; có bản trên USB.
- [ ] Tắt thông báo hệ điều hành, phóng chữ trình duyệt 125%, đóng tab thừa, sạc đầy pin.
- [ ] Người bấm và người nói thống nhất mốc 2:40 (quyết bỏ K5 hay không).
- [ ] Không có `OPENAI_API_KEY` hiện trên màn hình hay trong terminal đang chiếu.
