"""Vietnamese user-facing strings for the backend (01 §7).

Keep every string shown to users here so wording stays consistent and can be
reviewed in one place. Frontend strings live in ``web/src/lib/i18n.ts``.
Use ``str.format`` placeholders for numbers; numbers themselves come from code.
"""

from __future__ import annotations

# ------------------------------------------------------------------ errors (08 §1)
ERR_INTERNAL = "Có lỗi không mong muốn ở máy chủ. Vui lòng thử lại."
ERR_VALIDATION = "Dữ liệu gửi lên không đúng định dạng."
ERR_PARAM_OUT_OF_RANGE = "Giá trị tham số nằm ngoài khoảng cho phép."
ERR_UNAUTHENTICATED = "Thiếu thông tin người dùng (X-User)."
ERR_FORBIDDEN = "Vai trò của bạn không có quyền thực hiện thao tác này."
ERR_NOT_FOUND = "Không tìm thấy dữ liệu yêu cầu."
ERR_STATE_CONFLICT = "Không thể chuyển trạng thái này."
ERR_CONSTRAINT_VIOLATION = "Hành động vi phạm ràng buộc của chương trình sale."
ERR_STALE_INPUT = "Dữ liệu đã thay đổi sau khi tính. Vui lòng tính lại trước."
ERR_BLOCKING_DATA_ISSUE = "Thiếu dữ liệu bắt buộc nên chưa tính được."
ERR_AI_BUDGET_EXCEEDED = "Đã dùng hết hạn mức AI hôm nay."
ERR_AI_UNAVAILABLE = "Trợ lý đang ngoại tuyến."
ERR_NOT_IMPLEMENTED = "Chức năng này chưa được làm."

# ------------------------------------------------------------------ CLI
CLI_MIGRATE_DONE = "Đã migrate DuckDB tại {path}: {n_tables} bảng."
CLI_RESET_DONE = "Đã xóa và tạo lại DuckDB tại {path}."
CLI_RESET_CONFIRM = "Xóa toàn bộ dữ liệu trong {path}?"
CLI_RESET_ABORTED = "Đã hủy."
CLI_SEED_DONE = "Đã nạp dữ liệu khai báo mẫu (combo): {n} dòng."
CLI_NOT_IMPLEMENTED = "Lệnh '{command}' chưa làm (task {task}). Xem {plan}."

# ------------------------------------------------------------------ confidence labels
LABEL_VERIFIED = "Đã kiểm"
LABEL_REFERENCE = "Tham khảo"
LABEL_SCENARIO = "Kịch bản"

# ------------------------------------------------------------------ health
HEALTH_OK = "Hệ thống hoạt động bình thường."
HEALTH_DEGRADED = "Một số thành phần đang lỗi."
