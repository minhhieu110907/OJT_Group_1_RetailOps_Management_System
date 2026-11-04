# RetailOps V1.0 — Frontend Handoff & Design Freeze

Ngày rà soát: 04/11/2026  
Nguồn ưu tiên: RetailOps SRS V1.3 → UI Design Brief → thiết kế Stitch hiện tại  
Project: https://stitch.withgoogle.com/projects/201020714942235892

## 1. Kết luận điều hành

Khuyến nghị của vòng rà soát độc lập: **APPROVE WITH CONDITIONS** để Product Owner cân nhắc.

Không còn lỗi Critical/High đã xác minh trong các màn hình canonical. React có thể bắt đầu theo đúng danh sách canonical dưới đây. Hai điều kiện trước khi Product Owner khóa thiết kế:

1. Kiểm thử lại trên trình duyệt thực ở đúng 1366×768, 390×844 và 375×812; Stitch chỉ cung cấp 1280×1024, 768×1024 và 390×884 trong phiên kiểm tra.
2. Không dùng node AI cũ `8376d27274ea4d3fa5b2d77a572a1a61`; node canonical là `e3d4e1cbcdef45da899c1a2c1cfc505c`.

Hành vi backend như RBAC, transaction, idempotency, khóa đồng thời, hoàn tồn đúng một lần và session security chưa thể được chứng minh bằng mockup tĩnh; chúng phải được xác minh bằng contract và test khi triển khai.

## 2. Thay đổi hoàn tất trong vòng cuối

- Xóa hai bản POS dư và một Prototype POS; giữ duy nhất POS canonical `35a5c8cf7eb24600b23e02b1ba40b52a`.
- Chuẩn hóa màn hình đăng ký: bỏ “ca làm việc/ca trực”, đổi “hóa đơn POS” thành “đơn hàng POS”, loại mã trạng thái/ký hiệu kỹ thuật khỏi copy người dùng.
- Chuẩn hóa chi tiết/hủy đơn: bỏ mã SRS và HTTP; thay thông báo xung đột bằng hướng dẫn tiếng Việt; giữ nguyên quy tắc Staff/Admin và hoàn tồn một lần.
- Tạo P0 còn thiếu: “Lịch sử đơn hàng - Admin & Staff” (`de2d9ba46a41472ab94ec451ef36b216`). Sau kiểm tra lần đầu, đã sửa tiếp để sidebar Staff đúng quyền và loại bỏ ca quầy, mã SRS, trạng thái mô phỏng cùng nội dung ngoài phạm vi.
- Sửa lỗi tablet đã quan sát trên màn hình lịch sử đơn: dưới 1024 px chuyển bảng nhiều cột thành danh sách card có đủ trạng thái, tổng tiền và CTA “Xem chi tiết”; xác minh lại tại 768×1024 không còn cột bị khuất.
- Tạo phiên bản canonical mới cho trạng thái AI (`e3d4e1cbcdef45da899c1a2c1cfc505c`): copy tiếng Việt, “Đang xử lý dữ liệu...”, không lộ HTTP/error code/model/SQL/backend/rate-limit kỹ thuật.

## 3. Screen inventory và readiness

Tham chiếu desktop/responsive là tên màn hình và node ID trong cùng project Stitch. “Dùng chung” nghĩa là một component responsive, không yêu cầu tách thêm màn hình.

| # | Màn hình canonical | Node ID | SRS / FE | Quyền | Trạng thái quan trọng | Responsive | Sẵn sàng |
|---:|---|---|---|---|---|---|---|
| 1 | Đăng ký tài khoản nhân viên | `137cd9d8eccb40a0af2a8310a0e14cfc` | AUTH-01, FE-02 | Public | validation, trùng yêu cầu, chờ duyệt | Dùng chung | Ready |
| 2 | Trạng thái yêu cầu tài khoản | `223efd08b0c64d5782369aa13c23d734` | AUTH-01, AUTH-03, FE-02 | Public/Staff | pending, rejected, approved | Dùng chung | Ready |
| 3 | Đăng nhập | `ef6bd2859b55459ebed49b032a6d2ee2` | AUTH-02, FE-02 | Public | sai thông tin, khóa tạm do giới hạn, phiên không hợp lệ | Dùng chung | Ready |
| 4 | Quên và đặt lại mật khẩu | `ba2ebaf7df5b483db7e70b8d35d0ae` | AUTH-02, FE-02 | Public/Staff | gửi yêu cầu chung, token hợp lệ/hết hạn/đã dùng | Dùng chung | Ready |
| 5 | Duyệt tài khoản nhân viên | `5c982834bcbf41338ad436001217a78c` | AUTH-03, FE-02 | Admin | approve, reject, conflict đã xử lý | Dùng chung | Ready |
| 6 | Thông báo đăng ký mới | `9f9abef7ff2c40e2b0214932c18d6c35` | AUTH-05 | Admin | unread/read, mở hồ sơ chờ duyệt | Dùng chung | Ready |
| 7 | Không gian làm việc Staff | `b2b74ef2c1cf43d987935253dab4330a` | AUTH-04, FE-01 | Staff | navigation và dữ liệu được phép | Dùng chung | Ready |
| 8 | Quản lý sản phẩm | `097dfe3d431f4d71be781eb2bb6bbca7` | PROD-01, PROD-03, FE-03 | Admin | loading, empty, validation, active/inactive | Dùng chung | Ready |
| 9 | Chi tiết sản phẩm theo quyền | `ca878c4e3c4445378e3fcecff306de11` | PROD-04 | Admin/Staff | ẩn giá nhập/giá vốn với Staff | Dùng chung | Ready |
| 10 | Quản lý danh mục | `4f7ccec971fd49e185458bb48b7309d6` | PROD-02, FE-03 | Admin | active/inactive, đang được tham chiếu | Dùng chung | Ready |
| 11 | Quản lý nhà cung cấp | `a372854ea8cb4fa28cff45afda5fb9d9` | PUR-01, FE-03 | Admin | active/inactive, lịch sử vẫn giữ | Dùng chung | Ready |
| 12 | Quản lý nhập hàng | `1e4c9d936a5d42609bda1d08cfb84290` | PUR-02..05, FE-04 | Admin | draft, validation dòng trùng, confirm, cancel draft | Dùng chung | Ready |
| 13 | Trạng thái phiếu nhập | `beb30dc888f347a9a36eda96f0fff8fd` | PUR-02..04 | Admin | stale version, confirmed immutable, cancelled | Dùng chung | Ready |
| 14 | Tổng quan tồn kho | `ad58a10b28dd4972b951d17f8509b3df` | INV-01, INV-04 | Admin/Staff | lọc, low stock chỉ Product ACTIVE | Dùng chung | Ready |
| 15 | Điều chỉnh tồn kho | `f8281967f39e4d5b9d8ba1ffc3329445` | INV-02, FE-05 | Admin | expected version, no-op, stale conflict | Dùng chung | Ready |
| 16 | Lịch sử biến động kho — Admin | `4c4a8d754202427da4bfab5f4967918e` | INV-03, FE-05 | Admin | append-only, đầy đủ audit được phép | Dùng chung | Ready |
| 17 | Lịch sử biến động kho — Staff | `7d8faefbaa0248a180a544be4a0a8f94` | INV-03, FE-05 | Staff | không giá nhập/giá vốn/lý do riêng tư | Dùng chung | Ready |
| 18 | POS Terminal | `35a5c8cf7eb24600b23e02b1ba40b52a` | SALE-01, SALE-02, FE-06 | Admin/Staff | cart, out-of-stock, price changed, pending checkout | 390×884 đã kiểm tra | Ready |
| 19 | Trạng thái giao dịch POS | `bda1c3ce03d540c981c84b7f53c3c9b6` | SALE-02, SALE-05 | Admin/Staff | PRICE_CHANGED thân thiện, retry an toàn, kết quả cũ | Dùng chung | Ready |
| 20 | Lịch sử đơn hàng | `de2d9ba46a41472ab94ec451ef36b216` | SALE-03, FE-06 | Admin/Staff | loading, empty, error, filter, pagination | 390×884 và 768×1024 đã đo | Ready |
| 21 | Chi tiết và xác nhận hủy đơn | `338836136eb54b98b07f903dc1909183` | SALE-03, SALE-04, FE-06 | Admin/Staff | eligible/ineligible, reason required, conflict | Dùng chung | Ready |
| 22 | Xung đột giao dịch trọng yếu | `d34a6a74365749938979e9941083bf54` | PUR-03, INV-02, SALE-02/04/05 | Theo module | receipt, stock, checkout, cancel conflict | Dùng chung | Ready |
| 23 | Tổng quan cửa hàng | `a9a209601ec74abfad5b436c21f9354f` | ANA-01, FE-07 | Admin | kỳ/ngày kinh doanh, completed/cancelled definitions | Dùng chung | Ready |
| 24 | Phân tích doanh thu & đơn hàng | `88948c0e6a3f4597ac0c107ca8e58bf7` | ANA-01, FE-07 | Admin | kỳ, doanh thu, AOV, cancelled attribution | Dùng chung | Ready |
| 25 | Phân tích sản phẩm & tồn kho | `f499936b33f740b6afea1e30be65fe1b` | ANA-02..04, FE-07 | Admin | top/slow/low stock đúng định nghĩa | Dùng chung | Ready |
| 26 | Trợ lý AI RetailOps | `cc74fad786ce4b4ab6c5c063113caae2` | AI-01..03, FE-07 | Admin | read-only, evidence, suggestion only | Dùng chung | Ready |
| 27 | Trạng thái Trợ lý AI — canonical | `e3d4e1cbcdef45da899c1a2c1cfc505c` | AI-04, FE-07 | Admin | processing, insufficient evidence, timeout, quota, unavailable, denied | 390×884 đã đo | Ready |
| 28 | Trạng thái hệ thống dùng chung | `f2bbcdbbf8e04bf7b3cec64ed4b096d0` | FE-01, GOV-04 | Theo quyền | loading, empty, validation, conflict, permission, error | Dùng chung | Ready |

### Không canonical — không dùng khi code

| Màn hình | Node ID | Lý do |
|---|---|---|
| Trạng thái Trợ lý AI cũ | `8376d27274ea4d3fa5b2d77a572a1a61` | Còn mã HTTP, error code và thuật ngữ kỹ thuật; đã được thay thế bởi node `e3d4...` |

## 4. Ma trận SRS → màn hình → mức đáp ứng

| Nhóm SRS | Màn hình bằng chứng | Mức đáp ứng thiết kế |
|---|---|---|
| AUTH-01..05 | 1–7 | Đầy đủ P0; quyền Admin/Staff tách rõ |
| PROD-01..04 | 8–10 | Đầy đủ; Staff không nhận trường nhạy cảm |
| PUR-01..05 | 11–13, 22 | Đầy đủ luồng draft/confirm/cancel/history/conflict; không supplier reversal |
| INV-01..04 | 14–17, 22 | Đầy đủ P0; low-stock chỉ Product ACTIVE; Staff movement đã lọc |
| SALE-01..05 | 18–22 | Đầy đủ P0 sau khi thêm lịch sử đơn; không VAT/discount/refund/payment processing |
| ANA-01..04 | 23–25 | Đầy đủ P0; ANA-05 CSV là P1, không bắt buộc freeze |
| AI-01..04 | 26–27 | Đầy đủ P0; chỉ đọc, có evidence và các trạng thái lỗi an toàn |
| FE-01..07 / GOV-04 | 1–28 | Có coverage UI; contract và hành vi thật cần xác minh khi code |

## 5. Shared components cho React

| Component | Trách nhiệm | Ghi chú triển khai |
|---|---|---|
| `AppShell` | Header, sidebar, content, mobile navigation | Nhận `role`; menu từ allowlist, không chỉ CSS hide |
| `Sidebar` | Navigation Admin/Staff | Một component, hai cấu hình quyền |
| `PageHeader` | Title, breadcrumb, action slot | Chỉ một primary CTA khi cần |
| `DataTable` | Sort/filter/pagination/loading/empty/error | Desktop table; mobile chuyển card/list, không ép scroll toàn trang |
| `FilterBar` / `FilterDrawer` | Bộ lọc responsive | Drawer ở mobile, lưu trạng thái filter trong URL nếu phù hợp |
| `FormField` | Label, help, validation | Error cạnh field; không dựa duy nhất vào màu |
| `StatusBadge` | Active/inactive, draft/confirmed/cancelled, completed | Mapping màu/nhãn tập trung |
| `Dialog` | Confirm destructive action | Focus trap, Escape, return focus, CTA destructive rõ |
| `Drawer` | Filter/mobile cart | Không che CTA; body scroll lock |
| `AsyncState` | Loading/empty/error/permission/conflict | Copy tiếng Việt và một hành động an toàn |
| `POSCart` | Cart line, quantity, totals, checkout | Sticky summary/CTA mobile; giá chỉ là báo giá trước checkout |
| `PriceChangedDialog` | Hiển thị giá cũ/mới và xác nhận ý định mới | Không tự retry với ý định cũ |
| `EvidencePanel` | Kỳ dữ liệu, nguồn và giới hạn câu trả lời AI | Không lộ tool/SQL/model |
| `AIMessage` | User/assistant/loading/error | Processing copy cố định: “Đang xử lý dữ liệu...” |

## 6. Design tokens

### Màu canonical

| Token | Giá trị | Dùng cho |
|---|---|---|
| `color.primary` | `#087F5B` | CTA chính, active, focus accent |
| `color.secondary` | `#586574` | Text phụ, icon, border mạnh |
| `color.tertiary` | `#E7F4ED` | Surface xanh nhẹ, selected row, success-soft |
| `color.neutral` | `#242A30` | Text chính |
| `color.surface` | `#FFFFFF` | Page/card/dialog |

- Typography: Inter; heading 24/32 hoặc 20/28, body 14/20–16/24, label 12/16–14/20.
- Spacing scale: 4, 8, 12, 16, 24, 32 px; page gap ưu tiên 24 px desktop, 16 px mobile.
- Radius: 8 px cho field/button, 12 px cho card, 16 px cho dialog/drawer lớn.
- Shadow: tối thiểu; card ưu tiên border, dialog/drawer dùng shadow vừa phải.
- Focus: outline xanh có độ tương phản; không loại bỏ focus ring.
- Breakpoint triển khai đề xuất: `<640` mobile, `640–1023` tablet, `≥1024` desktop. Thiết kế phải co giãn liên tục, không phụ thuộc đúng một kích thước mẫu.

## 7. Critical workflows — trạng thái người dùng

### Login và phiên

1. Submit → loading, khóa submit lặp.
2. Sai thông tin → phản hồi chung, không tiết lộ email tồn tại.
3. Phiên không còn hợp lệ → “Phiên đăng nhập không còn hiệu lực. Vui lòng đăng nhập lại.”
4. Không hiển thị JWT, cookie, LocalStorage hoặc giải thích nội bộ.

### Purchase version conflict

- Giữ dữ liệu người dùng đã nhập để đối chiếu.
- Thông báo: “Phiếu nhập đã được cập nhật ở nơi khác. Hãy tải dữ liệu mới nhất trước khi tiếp tục.”
- CTA duy nhất: `Tải lại phiếu nhập`.
- Không cho sửa/hủy phiếu đã xác nhận.

### Inventory version conflict

- Không tự áp số đếm lên phiên bản mới.
- Hiển thị tồn hiện tại mới nhất và yêu cầu kiểm kê/đối chiếu lại.
- No-op: ghi nhận kết quả kiểm kê nhưng không mô tả như có biến động kho.

### POS PRICE_CHANGED

- Toàn bộ checkout bị từ chối; chưa tạo đơn/chưa trừ kho.
- Dialog so sánh giá đã xem và giá mới.
- Người dùng xác nhận giá mới rồi tạo ý định checkout mới; không tự động retry mù.

### Pending checkout

- Hiển thị đang xử lý và ngăn submit lặp.
- Nếu mất kết nối, không tuyên bố thất bại/thành công cho đến khi tra cứu kết quả theo contract.
- Không dùng mockup để khẳng định idempotency đã hoạt động.

### Order cancellation

- Staff: chính chủ, trạng thái Hoàn tất, không quá 15 phút và cùng ngày.
- Admin: mọi đơn Hoàn tất trong cùng ngày.
- Bắt buộc lý do, cảnh báo không thể hoàn tác, tải lại khi đơn đã được xử lý ở nơi khác.
- UI chỉ mô tả “tồn kho được hoàn trả một lần”; backend chịu trách nhiệm bảo đảm bất biến.

### AI

- Processing: “Đang xử lý dữ liệu...”
- Timeout: giải thích chưa nhận đủ phản hồi, CTA `Thử lại`.
- Quota: nói khi nào có thể thử lại nếu server cung cấp; không hard-code hạn mức vào UI.
- Insufficient evidence: nói rõ không đủ dữ liệu, không đưa kết luận chắc chắn.
- Service error: thông báo tạm thời không khả dụng, không lộ mã/error stack.
- Staff denied: giải thích chức năng chỉ dành cho Quản trị viên, CTA quay lại vùng được phép.

## 8. Responsive test matrix

| Viewport | Kết quả | Bằng chứng / giới hạn |
|---|---|---|
| 1280×1024 | VERIFIED đại diện | Preview desktop Stitch; dùng thay kích thước desktop hỗ trợ sẵn |
| 1366×768 | NOT VERIFIED | Stitch không cung cấp đúng viewport này trong phiên kiểm tra |
| 768×1024 | VERIFIED đại diện | Product Management và Lịch sử đơn hàng đo `scrollWidth = clientWidth`; các màn hình trọng yếu đã kiểm tra bằng preview |
| 390×884 | VERIFIED đại diện | POS, Product Management, AI và Lịch sử đơn hàng; không phát hiện tràn ngang trên các màn hình đã đo |
| 390×844 | NOT VERIFIED | Gần với 390×884 nhưng không được coi là bằng chứng tương đương |
| 375×812 | NOT VERIFIED | Chưa có viewport tương ứng trong Stitch preview |
| Bàn phím ảo mobile | NOT VERIFIED | Preview tĩnh không mô phỏng đáng tin cậy keyboard/visual viewport |

Acceptance test React bắt buộc bổ sung: mở keyboard ở search POS, form receipt, reason cancellation và AI input; xác minh input cùng CTA không bị che.

## 9. Rủi ro còn lại và mức chặn

| Mức | Rủi ro | Tác động | Có chặn code? |
|---|---|---|---|
| Medium | Chưa test đúng 1366×768, 390×844, 375×812 | Có thể lộ overflow/CTA bị che khi code thật | Không chặn dựng component; chặn PO freeze cuối |
| Medium | Keyboard mobile chưa kiểm tra | Search/form/checkout có thể bị che | Không chặn code; phải test trước UAT |
| Low | Node AI cũ vẫn tồn tại nhưng đã loại khỏi canonical handoff | Dev có thể chọn nhầm | Không, nếu tuân node ID canonical |
| Low | Một số nhãn vai trò vẫn dùng Admin/Staff theo từ vựng SRS | Chưa hoàn toàn thuần Việt | Không |
| Implementation | Static mockup không chứng minh RBAC/transaction/idempotency/concurrency | Rủi ro nghiệp vụ nếu frontend suy diễn | Không phải lỗi thiết kế; bắt buộc contract + test |

## 10. Quy tắc design freeze

- Chỉ code các node canonical trong mục 3.
- Không thêm VAT, discount, refund/return, real payment, shift, branch/multi-warehouse, supplier reversal hoặc AI write action.
- P1 `INV-05`, `ANA-05`, `ENG-10` không nằm trong acceptance P0.
- Các quyết định Technical Design còn mở (TD-01, TD-03, TD-04, TD-05) không được “chốt” bằng UI.
- Product Owner là người ra quyết định phê duyệt cuối cùng.
