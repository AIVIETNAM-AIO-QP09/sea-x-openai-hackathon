# web · MegaDay Twin frontend

React 18 + Vite + TypeScript (strict) + Tailwind 4 + TanStack Query + React Router 7. Code tiếng Anh, mọi chữ trên UI tiếng Việt (nằm ở `src/lib/i18n.ts`). Thiết kế màn hình theo [docs/dev-plan/09-giao-dien.md](../docs/dev-plan/09-giao-dien.md), hợp đồng API theo [08-api.md](../docs/dev-plan/08-api.md).

## Cài và chạy

Yêu cầu Node 22 trở lên (team dùng v24), npm 10 trở lên.

```bash
cd web
npm ci                  # cài đúng phiên bản trong package-lock.json
cp .env.example .env.local   # Windows: copy .env.example .env.local
npm run dev             # http://localhost:5173
```

Khi `npm run dev`, mọi request `/api/*` được proxy sang `VITE_PROXY_TARGET` (mặc định `http://localhost:8000`), nên backend chạy ở cổng 8000 là dùng được ngay, không cần CORS.

## Chế độ fixture (chưa có backend)

```bash
# .env.local
VITE_USE_FIXTURES=true
```

Hoặc chạy một lần: `VITE_USE_FIXTURES=true npm run dev` (PowerShell: `$env:VITE_USE_FIXTURES='true'; npm run dev`).

Client không gọi mạng mà đọc JSON trong `src/api/fixtures/`, lấy từ các ví dụ ở 08-api. Thanh trên cùng hiện nhãn "Dữ liệu mẫu" để không ai nhầm với số thật.

| Path | Fixture | Ghi chú |
|---|---|---|
| `/health` | `health.json` | `{"status":"ok","db":"ok","ai":"disabled"}` (01 §Tiêu chí) |
| `/me`, `/freshness`, `/live/status` | `me.json`, `freshness.json`, `live-status.json` | 08 §3.1, §3.13 |
| `/skus` | `skus.json` | dòng NOICHIEN2L đúng ví dụ 08 §3.4; các dòng khác là minh họa theo 6 nhân vật demo |
| `/recommendations`, `/recommendations/rec-551` | `recommendations.json`, `recommendation-rec-551.json` | ca CD002 ngày 11.11: `schedule_hours` thắng |
| `/scenarios/scn-2291` | `scenario-scn-2291.json` | 5 hành động; `pause` và `pause_until_restock` bị `campaign_must_run` |
| `/recommendations/rec-540`, `/scenarios/scn-2280` | `recommendation-rec-540.json`, `scenario-scn-2280.json` | minh họa: CD002 ngày thường, `continue` thắng |
| `/recommendations/rec-510`, `/scenarios/scn-2210` | `recommendation-rec-510.json`, `scenario-scn-2210.json` | minh họa: ví dụ trang 10 (ngưỡng 22,5 → 16,5 khi hàng dư 20.000đ) |
| `/alerts` | `alerts.json` | 08 §3.11 + 2 cảnh báo minh họa |

Màn So sánh: `/sku/NOICHIEN2L/compare`, `/campaign/CD002/compare`, `/campaign/CD002/compare?rec=rec-540`, `/campaign/VIDU-T10/compare?rec=rec-510`; `/compare` liệt kê cả ba. Ở chế độ fixture, thanh trượt chỉ ước tính bằng `src/lib/breakeven.ts`, không gọi `POST /scenarios/run`. Quyết định liên quan: [docs/quyet-dinh/M3-web.md](../docs/quyet-dinh/M3-web.md).

Thêm fixture: tạo file JSON trong `src/api/fixtures/` và thêm một dòng vào `FIXTURE_ROUTES` trong `src/api/client.ts`. Query string bị bỏ qua khi tra fixture. Test (`npm test`) luôn chạy ở chế độ fixture.

## Sinh type từ OpenAPI

```bash
npm run gen:api                                   # thử localhost:8000/api/v1/openapi.json rồi /openapi.json
OPENAPI_URL=http://host:8000/api/v1/openapi.json npm run gen:api
```

Kết quả ghi đè `src/api/schema.d.ts`. Khi backend chưa chạy, lệnh báo lỗi rõ ràng, thoát mã 1 và **không đụng** file hiện tại. Bản đang commit là schema tạm viết tay theo 08-api để code biên dịch được.

Code trong app chỉ import type qua `src/api/types.ts`. Sau khi sinh từ backend thật, chạy `npm run typecheck`; nếu tên schema Pydantic khác bản tạm, chỉ cần sửa alias trong `types.ts`.

## Script

| Lệnh | Việc |
|---|---|
| `npm run dev` | Dev server có HMR |
| `npm run build` | Typecheck rồi build ra `dist/` |
| `npm run preview` | Xem bản build |
| `npm test` | Vitest + Testing Library (jsdom), chạy một lần |
| `npm run test:watch` | Vitest chế độ theo dõi |
| `npm run lint` | ESLint, không cho phép cảnh báo |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run gen:api` | Sinh `src/api/schema.d.ts` |

Trước khi push: `npm run lint && npm run typecheck && npm test && npm run build`. CI (`.github/workflows/web.yml`) chạy đúng chuỗi này khi PR đụng `web/`.

## Biến môi trường

Xem `.env.example`. Chỉ biến có tiền tố `VITE_` vào bundle, nên **không bao giờ** đặt bí mật vào đây.

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `VITE_API_BASE_URL` | `/api/v1` | Gốc API |
| `VITE_PROXY_TARGET` | `http://localhost:8000` | Backend cho proxy dev |
| `VITE_USE_FIXTURES` | `false` | `true` = đọc fixture JSON |
| `VITE_DEV_USER`, `VITE_DEV_USER_NAME`, `VITE_DEV_ROLE` | `u-ops-1`, `Lan`, `operator` | Gửi qua header `X-User`/`X-Role` (08 §1) |
| `OPENAPI_URL` | trống | URL cho `gen:api` |

## Cấu trúc

```
src/
├─ main.tsx, routes.tsx, index.css   # điểm vào, bảng route (09 §1), token theme sáng/tối
├─ api/      client.ts (fetch + ApiError + fixture), queries.ts (hook TanStack Query),
│            types.ts (alias type), schema.d.ts (sinh), fixtures/*.json
├─ components/  AppShell (TopBar, SideNav, panel Trợ lý), badges, states (PageHeader, EmptyState, ErrorState, Skeleton, Banner, UpdatingRegion),
│               CitationChip, numbers (MoneyVND, Range), ZoneBar (SVG)
├─ pages/    ShiftOverviewPage, compare/ (So sánh 3 tầng, form quyết định), placeholders cho 6 màn còn lại
└─ lib/      i18n.ts, format.ts (tiền VND, giờ Asia/Ho_Chi_Minh, số lượng), breakeven.ts (hòa vốn 05 §7, cùng công thức backend),
            zoneBarText.ts, storage.ts, theme.ts, queryKeys.ts, config.ts
```

Theme: token CSS trên `:root` và `[data-theme='dark']`, map vào Tailwind bằng `@theme inline` (dùng `bg-surface`, `text-muted`, `border-border`...). Nút trên thanh trên cùng đổi Theo hệ thống / Sáng / Tối, lưu ở `localStorage` (bọc try/catch). `Ctrl+K` mở panel Trợ lý, `Esc` đóng.
