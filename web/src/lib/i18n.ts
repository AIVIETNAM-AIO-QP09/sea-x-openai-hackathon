// All user-facing Vietnamese strings live here (01 §7, 09 §5).
import type { ActionSpec, ComputeState, Confidence } from '../api/types';
import type { Role } from './config';
import { formatHourWindows, formatNumber } from './format';

export const viText = {
  app: {
    name: 'MegaDay Twin',
    shopName: 'Shop Gia Dụng Demo',
    event: 'Siêu sale 11.11',
    skipToContent: 'Bỏ qua tới nội dung chính',
  },
  nav: {
    label: 'Điều hướng chính',
    overview: 'Tổng quan ca',
    skuDetail: 'Chi tiết SKU',
    compare: 'So sánh lựa chọn',
    import: 'Nhập dữ liệu',
    alerts: 'Cảnh báo',
    decisions: 'Nhật ký quyết định',
    assistant: 'Trợ lý AI',
    settings: 'Cài đặt',
    collapse: 'Thu gọn menu',
    expand: 'Mở rộng menu',
  },
  topBar: {
    dataUntil: (time: string) => `Dữ liệu tới ${time}`,
    alerts: (n: number) => `Cảnh báo ${n}`,
    alertsAria: (n: number) => `${n} cảnh báo đang mở`,
    openAssistant: 'Mở Trợ lý (Ctrl+K)',
    fixtureMode: 'Dữ liệu mẫu',
    fixtureModeHint: 'Đang chạy chế độ fixture: số liệu lấy từ ví dụ trong tài liệu API, không phải từ backend.',
  },
  role: {
    operator: 'Vận hành',
    lead: 'Trưởng nhóm',
    viewer: 'Xem',
  } satisfies Record<Role, string>,
  theme: {
    label: 'Giao diện',
    system: 'Theo hệ thống',
    light: 'Sáng',
    dark: 'Tối',
  },
  freshnessSource: {
    orders: 'Đơn',
    ads: 'Ads',
    inventory: 'Tồn',
    cost: 'Giá vốn',
  } as Record<string, string>,
  freshnessStatus: {
    fresh: 'mới',
    stale: 'cũ',
    partial: 'thiếu một phần',
    missing: 'chưa có',
  } as Record<string, string>,
  freshnessTooltip: (label: string, time: string, status: string) => `${label} tới ${time} · ${status}`,
  confidence: {
    verified: { label: 'Đã kiểm', hint: 'Dự báo đã được kiểm trên dữ liệu cũ và đạt ngưỡng sai số' },
    reference: { label: 'Tham khảo', hint: 'Đã kiểm nhưng chưa đạt ngưỡng, hoặc bối cảnh mới' },
    scenario: { label: 'Kịch bản', hint: 'Chưa đủ dữ liệu, kết quả dựa trên giả định' },
  } satisfies Record<Confidence, { label: string; hint: string }>,
  computeState: {
    fresh: 'Mới',
    queued: 'Chờ tính',
    computing: 'Đang cập nhật',
    stale: 'Dữ liệu cũ',
    failed: 'Tính lỗi',
  } satisfies Record<ComputeState, string>,
  action: (a: Pick<ActionSpec, 'kind' | 'pct' | 'windows_local'>): string => {
    switch (a.kind) {
      case 'continue':
        return 'Tiếp tục';
      case 'pause':
        return 'Tạm dừng';
      case 'reduce_budget':
        return a.pct != null ? `Giảm ngân sách ${formatNumber(a.pct)}%` : 'Giảm ngân sách';
      case 'schedule_hours':
        return a.windows_local?.length ? `Chỉ chạy ${formatHourWindows(a.windows_local)}` : 'Chỉ chạy theo khung giờ';
      case 'pause_until_restock':
        return 'Tạm dừng tới khi hàng về';
    }
  },
  recommendationStatus: {
    undetermined: 'Chưa phân định',
    none_meets_goal: 'Chưa đạt mục tiêu',
  },
  overview: {
    needsAttention: (n: number) => `Cần xem ngay (${n})`,
    allSkus: (n: number) => `Toàn bộ SKU (${n})`,
    columns: {
      sku: 'SKU',
      stock: 'Tồn',
      cover: 'Đủ bán (giờ)',
      soldToday: 'Bán hôm nay',
      recommendation: 'Đề xuất',
      confidence: 'Tin cậy',
      updated: 'Cập nhật',
    },
    stockLine: (stock: string, cover: string) => `Còn ${stock} · đủ bán khoảng ${cover} giờ`,
    gainLine: (amount: string) => `Lợi hơn ~${amount}`,
    alertCount: (n: number) => `${n} cảnh báo`,
    deviation: {
      on_track: 'Bán đúng nhịp',
      below_forecast: 'Bán thấp hơn dự báo',
      above_forecast: 'Bán cao hơn dự báo',
    } as Record<string, string>,
    compare: 'So sánh',
    noCampaign: 'Không chạy ads',
    nothingToReview: (time: string) => `Không có SKU nào cần xem ngay. Lần tính gần nhất lúc ${time}.`,
    emptyTitle: 'Chưa có dữ liệu SKU',
    emptyBody: 'Nạp lịch sử đơn hàng, tồn kho và giá vốn để app bắt đầu tính đề xuất.',
    emptyAction: 'Nhập dữ liệu',
  },
  pages: {
    overview: {
      title: 'Tổng quan ca',
      description: 'SKU nào cần xem ngay, xếp theo mức ưu tiên. Bấm "So sánh" để xem lý do và các lựa chọn.',
    },
    skuDetail: {
      title: 'Chi tiết SKU',
      description: 'Đường bán theo giờ, tồn kho, dự báo, chiến dịch và lịch sử quyết định của một SKU.',
      emptyTitle: 'Màn này đang được xây dựng',
      emptyBody: 'Biểu đồ bán, tồn và khoảng dự báo sẽ có ở mốc sau. Hiện có thể xem SKU ở Tổng quan ca.',
    },
    compare: {
      title: 'So sánh lựa chọn',
      description: 'Kết luận, lý do và chi tiết kiểm tra cho từng hành động: tiếp tục, giảm, chạy theo khung giờ hay tạm dừng.',
      emptyTitle: 'Màn này đang được xây dựng',
      emptyBody: 'Thanh vùng quyết định và thẻ so sánh 5 hành động sẽ có ở mốc sau.',
      target: (target: string) => `Đối tượng: ${target}`,
    },
    import: {
      title: 'Nhập dữ liệu',
      description: 'Tải file, ghép cột, ghép sản phẩm và xem lỗi dữ liệu trước khi nạp.',
      emptyTitle: 'Chưa có lần nhập nào',
      emptyBody: 'Wizard 5 bước (tải file, ghép cột, ghép sản phẩm, kiểm tra, xong) sẽ có ở mốc sau.',
    },
    alerts: {
      title: 'Cảnh báo',
      description: 'Cảnh báo gom theo tình huống, xếp theo ảnh hưởng, kèm kết quả điều tra.',
      emptyTitle: 'Màn này đang được xây dựng',
      emptyBody: 'Khi tồn sắp hết, bán lệch dự báo hoặc dữ liệu trễ, cảnh báo sẽ hiện ở đây kèm nút Đã xem, Ẩn 1 giờ và Điều tra. Số cảnh báo đang mở hiện ở thanh trên cùng.',
    },
    decisions: {
      title: 'Nhật ký quyết định',
      description: 'Duyệt, theo dõi và xem lại các quyết định; tạo ghi chú bàn giao ca.',
      emptyTitle: 'Chưa có quyết định nào',
      emptyBody: 'Quyết định được tạo từ màn So sánh lựa chọn. Thao tác ở bản này là mô phỏng, chưa gửi lên sàn.',
    },
    assistant: {
      title: 'Trợ lý AI',
      description: 'Hỏi what-if hoặc "vì sao" bằng tiếng Việt. Mọi con số Trợ lý nói đều có nguồn và đã được kiểm.',
      emptyTitle: 'Trợ lý chưa sẵn sàng',
      emptyBody: 'Trợ lý đang ngoại tuyến. Mọi số liệu vẫn xem được ở các màn chính.',
      panelTitle: 'Trợ lý',
      close: 'Đóng Trợ lý',
      openFull: 'Mở toàn màn',
    },
    settings: {
      title: 'Cài đặt mục tiêu và tham số',
      description: 'Mục tiêu shop, danh mục tham số, phiếu điểm model và điều khiển demo.',
      emptyTitle: 'Chưa có cấu hình',
      emptyBody: 'Bốn tab Mục tiêu, Tham số, Phiếu điểm model và Demo sẽ có ở mốc sau.',
    },
    notFound: {
      title: 'Không tìm thấy trang',
      description: 'Đường dẫn này không có trong app.',
      back: 'Về Tổng quan ca',
    },
  },
  state: {
    loading: 'Đang tải',
    retry: 'Thử lại',
    errorTitle: 'Không tải được dữ liệu',
    errorCode: (code: string) => `Mã lỗi: ${code}`,
  },
  errors: {
    network: 'Không kết nối được tới máy chủ. Kiểm tra backend đã chạy ở cổng 8000, hoặc bật chế độ dữ liệu mẫu (VITE_USE_FIXTURES=true).',
    http: (status: number) => `Máy chủ trả lỗi ${status}. Thử lại sau ít phút.`,
    fixtureMissing: (path: string) => `Chế độ dữ liệu mẫu chưa có fixture cho ${path}.`,
  },
} as const;
