# MegaDay Twin

Trợ lý ra quyết định quảng cáo cho người vận hành shop trên Shopee. Khi nhu cầu và tồn kho thay đổi giữa mùa sale, app trả lời câu hỏi **"lúc này nên tiếp tục hay tạm dừng quảng cáo?"**. Câu trả lời dựa trên tồn kho, giá vốn, lịch hàng về và mục tiêu của shop, chứ không chỉ dựa trên ROAS sàn báo.

Điểm khác biệt cốt lõi: **AI không thể bịa số**. Lớp AI (OpenAI) hiểu câu hỏi tiếng Việt, điều tra và giải thích. Mọi con số nó nói ra đều đến từ công cụ đã được chấm điểm, được kiểm tự động trước khi hiển thị, và bấm vào được để xem nguồn. AI không tự bật/tắt quảng cáo; mọi hành động cần người duyệt.

> Dự án cho SEA × OpenAI Hackathon. Phạm vi bản hackathon: 1 shop, 1 sàn (Shopee), dữ liệu nạp bằng file, kịch bản mega sale 11.11 mô phỏng.

## Trạng thái

| Phần | Trạng thái | Ở đâu |
|---|---|---|
| Tài liệu sản phẩm (tính năng, hoàn cảnh, điều kiện sử dụng) | Có | [MegaDay-Twin-Tinh-nang-hoan-canh-va-dieu-kien-su-dung.pdf](MegaDay-Twin-Tinh-nang-hoan-canh-va-dieu-kien-su-dung.pdf) |
| Plan kỹ thuật đầy đủ (14 file) | Có | [docs/dev-plan/](docs/dev-plan/README.md) |
| Bộ sinh dữ liệu giả lập có đáp án | Có, chạy được | [mock-data/](mock-data/README.md) |
| Backend (FastAPI + DuckDB + OpenAI) | Chưa bắt đầu, mốc M0 | `backend/` |
| Frontend (React + Vite) | Chưa bắt đầu, mốc M0 | `web/` |

## Kiến trúc tóm tắt

```
Người vận hành ── hỏi bằng lời / ảnh ──▶  LỚP AI (OpenAI: function calling + kiểm số)
                                              │ chỉ đọc số qua công cụ
       ┌──────────────────────────────────────┼──────────────────────────────┐
       ▼                                      ▼                              ▼
① Dữ liệu ──▶ ② Mô hình ──▶ ③ Quyết định ──▶ ⑤ Giao diện 3 tầng ──▶ người duyệt ──▶ thao tác (mô phỏng)
 adapter,      dự báo có      mục tiêu, tham số,   kết luận 3 giây,
 ghép SKU,     phiếu điểm,    mô phỏng 5 hành động, lý do, chi tiết
 kiểm lỗi,     iROAS,         ngưỡng hòa vốn
 bỏ PII        kinh tế
       ▲                                                                     │
       └──────────── kết quả thật sau ca quay về chấm điểm lại ◀─────────────┘
                     ④ Quản trị: nhật ký quyết định, phiên bản, phân quyền
```

Chi tiết: [docs/dev-plan/01-kien-truc-va-cong-nghe.md](docs/dev-plan/01-kien-truc-va-cong-nghe.md).

## Cấu trúc repo

```
.
├─ README.md                      # file này
├─ MegaDay-Twin-...pdf            # tài liệu sản phẩm gốc
├─ docs/dev-plan/                 # plan kỹ thuật: kiến trúc, dữ liệu, mô hình, AI, API, UI, lộ trình
├─ mock-data/                     # bộ sinh dữ liệu shop giả lập (Node.js, không thư viện ngoài)
│  ├─ generate.js                 # sinh dữ liệu → mock-data/out/<cỡ>/
│  ├─ replay.js                   # phát lại ngày 11.11 theo giờ
│  ├─ config.json
│  └─ src/
├─ backend/                       # (sẽ tạo ở M0) Python 3.11, FastAPI, DuckDB
│  ├─ app/{core,ingest,warehouse,panel,forecast,ads_effect,economics,
│  │       simulator,orchestrator,governance,ai,live,api}/
│  ├─ tests/{unit,integration,e2e}/
│  └─ eval/                       # chấm điểm bằng ground_truth
└─ web/                           # (sẽ tạo ở M0) React 18, Vite, TypeScript, Tailwind
   └─ src/{pages,components,api,lib}/
```

Cây thư mục chi tiết tới từng file nằm ở [01 · Kiến trúc và công nghệ, mục 4](docs/dev-plan/01-kien-truc-va-cong-nghe.md).

## Bắt đầu nhanh

### Yêu cầu

| Công cụ | Phiên bản | Dùng cho |
|---|---|---|
| Git | bất kỳ | |
| Node.js | ≥ 18 (team đang dùng v24) | `mock-data`, `web` |
| Python | 3.11 | `backend` |
| [uv](https://docs.astral.sh/uv/) | mới nhất | quản lý môi trường Python |
| OpenAI API key | | lớp AI (app vẫn chạy đủ khi tắt AI) |

Cài trên Windows:

```powershell
winget install --id Python.Python.3.11 -e
winget install --id astral-sh.uv -e
# mở terminal mới rồi kiểm tra
python --version
uv --version
node --version
```

### 1. Lấy code

```bash
git clone https://github.com/AIVIETNAM-AIO-QP09/sea-x-openai-hackathon.git
cd sea-x-openai-hackathon
```

### 2. Sinh dữ liệu giả lập

Dữ liệu không được commit lên repo. Mỗi người tự sinh; cùng seed thì cả team ra cùng một bộ.

```bash
cd mock-data
node generate.js --size nho      # 30 SKU, < 1 giây — dùng khi dev
node generate.js --size demo     # 300 SKU, ~2 giây, ~60 MB — dùng để demo và chấm điểm
```

Kết quả nằm ở `mock-data/out/<cỡ>/`. Cuối lệnh có phần "Kiểm nhanh kịch bản 11.11" để xác nhận dữ liệu đúng.

### 3. Phát lại ngày 11.11 (chế độ live)

```bash
node replay.js --size demo --interval 20    # mỗi giờ mô phỏng = 20 giây
node replay.js --size demo --from 9         # bắt đầu từ 9h sáng cho demo ngắn
```

Dữ liệu "đang về" được ghi vào `mock-data/out/demo/live_stream/`, kèm `trang_thai.json` cho biết đã phát tới giờ nào. Báo cáo ads trễ 2 giờ như thật.

### 4. Backend và frontend

Phần này sẽ chạy được sau mốc M0. Lệnh dự kiến theo plan:

```powershell
# Backend
cd backend
uv venv --python 3.11
uv sync
copy .env.example .env                                  # điền OPENAI_API_KEY
uv run python -m app.cli migrate
uv run python -m app.cli ingest --dir ../mock-data/out/demo
uv run python -m app.cli backtest
uv run python -m app.cli estimate-ads
uv run uvicorn app.main:app --reload --port 8000        # http://localhost:8000/docs

# Frontend (terminal khác)
cd web
npm install
npm run gen:api                                         # sinh type từ openapi.json
npm run dev                                             # http://localhost:5173
```

Kiểm tra trước khi push:

```bash
cd backend && uv run ruff check && uv run mypy app && uv run pytest
cd web && npm test
```

### Biến môi trường

Backend đọc `backend/.env`. Mẫu đầy đủ ở [01 · mục 6](docs/dev-plan/01-kien-truc-va-cong-nghe.md). Các biến quan trọng:

| Biến | Ý nghĩa |
|---|---|
| `OPENAI_API_KEY` | Key OpenAI. **Không commit.** |
| `OPENAI_MODEL_REASONING` / `OPENAI_MODEL_FAST` / `OPENAI_MODEL_EMBED` | Tên model theo từng việc. Không hardcode trong code; kiểm bảng giá hiện tại trước khi chọn |
| `AI_ENABLED` | `false` thì app vẫn chạy đủ, chỉ tắt phần hỏi đáp |
| `AI_DEMO_CACHE` | Dùng câu trả lời đã cache cho kịch bản demo |
| `DATA_DIR`, `LIVE_DIR` | Thư mục dữ liệu lịch sử và dữ liệu live |
| `DUCKDB_PATH` | Mặc định `data/megaday.duckdb` |

## Dữ liệu giả lập

Một shop đồ gia dụng và quà tặng trên Shopee, có 120 ngày lịch sử theo giờ (14/07 → 10/11/2026) và ngày 11.11 để phát lại. Doanh số sinh theo cơ chế giống thật: nhịp giờ, ngày đôi, mùa vụ, trend, voucher, quảng cáo có bão hòa và tác dụng kéo dài, hết hàng, thứ hạng tự nhiên.

- **File đầu vào** (cái app được đọc): đơn hàng, báo cáo ads, sheet tồn kho, giá vốn gõ tay, cấu trúc chiến dịch, cam kết sale 11.11. Các file được làm bẩn có chủ ý (múi giờ UTC, đơn trùng, tồn âm, tên lệch, PII giả, một ghi chú prompt injection).
- **Đáp án** (`ground_truth/`): nhu cầu thật kể cả lúc hết hàng, iROAS thật, bảng ghép SKU đúng, danh sách lỗi cài sẵn. ROAS sàn phóng đại trung bình khoảng 1,47 lần so với iROAS thật.
- **6 nhân vật demo** cài sẵn câu chuyện cho 11.11: bình nước viral, nồi chiên sắp cạn, áo size M hết hàng, cốc meme trend nguội, đèn Tết tồn nhiều, máy hút bụi mới ra.

Chi tiết: [mock-data/README.md](mock-data/README.md).

## Tài liệu

| Tài liệu | Dành cho |
|---|---|
| [docs/dev-plan/README.md](docs/dev-plan/README.md) | Mục lục plan kỹ thuật, đọc theo vai trò |
| [00 · Tổng quan](docs/dev-plan/00-tong-quan.md) | Mọi người, đọc đầu tiên |
| [12 · Lộ trình và phân việc](docs/dev-plan/12-lo-trinh-va-phan-viec.md) | Mọi người: mốc, bảng task, người phụ trách, lịch 10 ngày |
| [11 · Kiểm thử và chấm điểm](docs/dev-plan/11-kiem-thu-va-cham-diem.md) | Chấm điểm bằng `ground_truth`, kịch bản diễn tập demo |
| [13 · Rủi ro và câu hỏi mở](docs/dev-plan/13-rui-ro.md) | Những điều team cần chốt |
| [mock-data/README.md](mock-data/README.md) | Định dạng file, lỗi cài sẵn, mô hình sinh dữ liệu |
| [Cẩm nang pitch](https://claude.ai/artifact/NuSEaHjNHnzrhKknD4smWU) | Pitch lead (cần chủ doc chia sẻ quyền xem) |

## Mốc

| Mốc | Qua mốc khi |
|---|---|
| M0 · Khung dự án | `backend` + `web` chạy, CI xanh, DuckDB đủ bảng |
| M1 · Dữ liệu sạch | Nạp đủ 7 file, ghép SKU tự động ≥ 90%, bắt đủ 12 lỗi cài sẵn |
| M2 · Dự báo và chấm điểm | Tốt hơn baseline ≥ 15% WAPE trên đợt 10.10, mọi SKU có nhãn tin cậy |
| M3 · Quyết định | Mô phỏng < 1 giây; ca nồi chiên 11.11 ra đúng `schedule_hours` |
| M4 · AI và live | Phát lại 11.11 chạy, AI điều tra đúng ca size M, kiểm số 100% |
| M5 · Demo | Diễn tập đạt 2 lần liên tiếp, có video dự phòng |

Plan hiện vượt công suất 4 dev × 10 ngày. Xem 3 phương án xử lý ở đầu [file 12](docs/dev-plan/12-lo-trinh-va-phan-viec.md).

## Quy ước làm việc

| Việc | Quy ước |
|---|---|
| Nhánh | `feat/<MÃ>-mo-ta-ngan`, ví dụ `feat/ING-03-ads-utc`. Sửa lỗi: `fix/<MÃ>-...` |
| Commit | Dòng đầu ≤ 72 ký tự, có mã task, ví dụ `ING-03: chuyển giờ báo cáo ads từ UTC` |
| Pull request | ≤ 400 dòng đổi (không tính dữ liệu và file sinh). Mô tả làm gì, test gì, ảnh chụp nếu là UI |
| Review | 1 người duyệt trong 4 giờ làm việc. D1 ↔ D2 review chéo dữ liệu/model; D3 ↔ D4 review chéo API/UI |
| `main` | Được bảo vệ, chỉ merge qua PR có CI xanh |
| Definition of Done | Code + test + CI xanh + đã chạy với dữ liệu `demo` + cập nhật docs nếu đổi hợp đồng |

Mã task (`INF`, `ING`, `PNL`, `FC`, `ADS`, `ECO`, `SIM`, `ORC`, `AI`, `API`, `WEB`, `GOV`, `LIVE`, `EVAL`, `DEMO` + số) lấy từ bảng task trong file 12.

## Nguyên tắc bắt buộc

1. **AI không bịa số.** Mọi con số AI nói ra phải đến từ kết quả công cụ và qua bước kiểm số. Xem [07 · Lớp AI](docs/dev-plan/07-lop-ai.md).
2. **Không rò đáp án.** Code trong `backend/app/` không được đọc `mock-data/out/*/ground_truth/`. Chỉ `backend/eval/` được đọc, và có test chặn.
3. **Người duyệt mọi hành động.** AI chỉ đề xuất tham số (`set_by=ai_suggested`); không tự tạo mục tiêu, không tự thao tác quảng cáo.
4. **Bỏ PII ngay khi nhập.** Tên, số điện thoại, địa chỉ người mua không được lưu vào DB và không gửi lên OpenAI.
5. **Dữ liệu ngoài là dữ liệu, không phải lệnh.** Ghi chú khách, tên sản phẩm, nội dung file luôn được bọc nhãn untrusted khi đưa cho AI.
6. **Không commit bí mật và dữ liệu sinh.** `.env`, `mock-data/out/`, `backend/data/` đã nằm trong `.gitignore`.
7. **Trung thực về độ bất định.** Mọi con số có nhãn Đã kiểm / Tham khảo / Kịch bản; dữ liệu mô phỏng luôn được gọi là mô phỏng.

## Việc đầu tiên

1. Đọc [00 · Tổng quan](docs/dev-plan/00-tong-quan.md), [12 · Lộ trình](docs/dev-plan/12-lo-trinh-va-phan-viec.md) và file của vai trò mình (bảng "Đọc theo vai trò" trong [docs/dev-plan/README.md](docs/dev-plan/README.md)).
2. Chốt các câu hỏi mở ở [13 · Rủi ro và câu hỏi mở](docs/dev-plan/13-rui-ro.md): độ dài hackathon, số người, phương án công suất, nơi deploy.
3. Cài Python 3.11 + uv, chạy `node generate.js --size nho` để có dữ liệu.
4. Bắt đầu các task M0 (`INF-*`) trong file 12: khung `backend/` và `web/`, CI, migrate DuckDB, test chống rò `ground_truth`.
