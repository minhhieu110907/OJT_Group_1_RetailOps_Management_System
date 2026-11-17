# RetailOps V1.0 — Báo Cáo QA Tổng Hợp & Sổ Tay Trình Diễn Demo (Sprint 3)

**Hệ thống:** RetailOps Management System V1.0  
**Mã Task LMS:** `T04ABDD` — `[S3] Báo cáo QA và tài liệu demo`  
**Kỹ sư phụ trách:** Vũ Hoàng Lan Anh  
**Mã sinh viên:** `B25DTCN143`  
**Hợp đồng & Cổng kiểm soát:** `GATE-E2E, DEPLOY`  
**Mốc kế hoạch Sprint:** 24/11/2026 · **Mốc Trình diễn Demo Chính thức:** 27/11/2026<br>
**Nhánh Git:** `feature/t04abdd-qa-report-and-demo`<br>
**Base Commit (develop):** `9684882` (*Merge PR #67; cập nhật tích hợp PR #73 tại `00b6c56`*)<br>
**Trạng thái Bàn giao Task:** **READY FOR LEAD REVIEW**<br>

---

## MỤC LỤC
1. [Thông Tin Quản Lý Tài Liệu & Phạm Vi Task T04ABDD](#1-thông-tin-quản-lý-tài-liệu--phạm-vi-task-t04abdd)
2. [Phần I — Báo Cáo QA Tổng Hợp Sprint 3](#phần-i--báo-cáo-qa-tổng-hợp-sprint-3)
   - 2.1. [Bảng Đối Soát Sáp Nhập PR & Commit trên Develop](#21-bảng-đối-soát-sáp-nhập-pr--commit-trên-develop)
   - 2.2. [Tổng Hợp Bằng Chứng Kiểm Thử & Độ Phủ Toàn Hệ Thống](#22-tổng-hợp-bằng-chứng-kiểm-thử--độ-phủ-toàn-hệ-thống)
   - 2.3. [Sổ Cái Theo Dõi Lỗi Hợp Nhất (Consolidated Defect Ledger)](#23-sổ-cái-theo-dõi-lỗi-hợp-nhất-consolidated-defect-ledger)
   - 2.4. [Đánh Giá Cổng Chất Lượng & Mức Độ Sẵn Sàng (Release Gate Assessment)](#24-đánh-giá-cổng-chất-lượng--mức-độ-sẵn-sàng-release-gate-assessment)
3. [Phần II — Sổ Tay & Kịch Bản Trình Diễn Demo (Reproducible Demo Guide)](#phần-ii--sổ-tay--kịch-bản-trình-diễn-demo-reproducible-demo-guide)
   - 3.1. [Checklist Tái Lập Môi Trường Chuẩn (Host & Docker Compose)](#31-checklist-tái-lập-môi-trường-chuẩn-host--docker-compose)
   - 3.2. [Dữ Liệu Seed Nền Tảng & Quy Trình Chuẩn Bị Dữ Liệu Nghiệp Vụ Mẫu](#32-dữ-liệu-seed-nền-tảng--quy-trình-chuẩn-bị-dữ-liệu-nghiệp-vụ-mẫu)
   - 3.3. [Kịch Bản Trình Diễn Chi Tiết & Phân Công Người Phụ Trách (6 Phân Cảnh)](#33-kịch-bản-trình-diễn-chi-tiết--phân-công-người-phụ-trách-6-phân-cảnh)
   - 3.4. [Giới Hạn Đã Biết & Kịch Bản Dự Phòng Rủi Ro (Fallback Plan)](#34-giới-hạn-đã-biết--kịch-bản-dự-phòng-rủi-ro-fallback-plan)

---

## 1. Thông Tin Quản Lý Tài Liệu & Phạm Vi Task T04ABDD

### 1.1. Mục đích và Định hướng
Tài liệu này được lập theo chuẩn Definition of Done (DoD) của Sprint 3 nhằm đáp ứng hai mục tiêu cốt lõi:
1. **Báo cáo QA Cấp Release (Consolidated QA Report):** Tổng hợp và đối soát toàn bộ các kết quả kiểm thử từ các thành viên trong nhóm (`T3C9972`, `T3C9970`, `T04AABC`, `T04AAD7`), rà soát các PR đã sáp nhập vào `develop`, tổng hợp sổ cái theo dõi lỗi (Defect Ledger) và đánh giá khách quan mức độ sẵn sàng cho đợt phát hành và nghiệm thu.
2. **Kịch bản Demo Khả lặp (Reproducible Demo Playbook):** Cung cấp tài liệu chỉ dẫn từng bước giúp kỹ sư và các bên liên quan có thể tái lập hệ thống từ đầu trên máy tính cá nhân, nạp dữ liệu hạt giống và thực hiện bài thuyết trình demo các phân cảnh nghiệp vụ phục vụ buổi nghiệm thu ngày **27/11/2026**.

### 1.2. Nguyên tắc Bắt buộc
- **Trung thực dựa trên bằng chứng (Evidence-Based — No Fake PASS):** Chỉ ghi nhận trạng thái kiểm chứng khi có kết quả test thực tế; phân định rành mạch giữa Unit/API test, MySQL integration test, Browser manual protocol và Staging verification.
- **Bảo mật thông tin (Zero Secret Leakage):** Mọi cấu hình, tài khoản mẫu trong tài liệu chỉ mang tính chất minh họa cục bộ trong môi trường development/demo từ `.env.example`. Tuyệt đối không chứa mật khẩu, JWT token hay secret key production thật.
- **Tuân thủ kiến trúc và hợp đồng hệ thống:** Bám sát cấu hình Docker Compose thực tế (`compose.yaml`), hợp đồng API (`contracts/openapi.yaml`) và quy trình trong `README.md`.

---

## Phần I — Báo Cáo QA Tổng Hợp Sprint 3

### 2.1. Bảng Đối Soát Sáp Nhập PR & Commit trên Develop

Bảng đối soát ghi nhận các Pull Request đã sáp nhập vào nhánh `develop` tính đến thời điểm lập báo cáo:

| PR # | Nhánh Feature Nguồn | Mã Task LMS | Tóm Tắt Tính Năng & Phạm Vi | Kỹ Sư Phụ Trách | Commit Merge | Trạng Thái Đối Soát |
|:---:|:---|:---:|:---|:---:|:---:|:---:|
| **#60** | `feature/T04A92B-sales-analytics` | `T04A92B` | API Analytics Doanh thu và Đơn hàng (`/api/v1/analytics/sales`), tính AOV làm tròn chuẩn, lọc múi giờ VN | Na Na | `51d005f` | **MERGED & VERIFIED** |
| **#61** | `feature/T04AA36-dashboard-api` | `T04AA36` | API Admin Dashboard (`/api/v1/dashboard`), tổng hợp doanh thu, đếm cảnh báo tồn kho, top sản phẩm | Na Na | `ed52c74` | **MERGED & VERIFIED** |
| **#62** | `feature/t04a869-t04a883-pos-checkout-order-cancel` | `T04A869`<br>`T04A883` | POS Checkout & Hủy đơn hàng giao dịch nguyên tử, tích hợp trừ/hoàn kho, ghi nhận `StockMovement` | Hiếu / Phú | `b0d4dc9` | **MERGED & VERIFIED** |
| **#63** | `feature/T04A996-docs-and-uat` | `T04A996` | Khởi tạo Khung UAT Sprint 3, sửa Runbook Nginx/Docker, đối soát 24 kịch bản UAT và Defect Ledger ban đầu | Lan Anh | `f1ced70` | **MERGED & VERIFIED** |
| **#64** | `feature/t04a89d--inventory-storage-management` | `T04A89D` | Quản lý kho lưu trữ, kiểm kê điều chỉnh tồn kho, định danh vị trí lưu kho | Hiếu | `b8cbc9b` | **MERGED & VERIFIED** |
| **#65** | `feature/t3c9970-test-cases` | `T3C9970` | Bộ kiểm thử 40 test cases cho Inventory & Duyệt phiếu nhập (`POST /confirm`), kiểm toán workbook | Dương / Lâm | `5bf2d47` | **MERGED & VERIFIED** |
| **#66** | `feature/T04AAD7-qa-product-order-analytics` | `T04AAD7` | Báo cáo đối soát kiểm thử chéo Product ↔ Order ↔ Analytics; cô lập dọn dẹp MySQL theo run-scope | Na Na | `55ebc43` | **MERGED & VERIFIED** |
| **#67** | `feature/T04A947-sales-analytics-api` | `T04A947` | Hoàn thiện API Analytics Sản phẩm (Top & Slow selling products), thực thi dọn dẹp an toàn MySQL | Dương | `9684882` | **MERGED & VERIFIED** |
| **#68** | `feature/t3c9972-module-test-cases-and-log` | `T3C9972` | 36 Test case specifications & 68 execution logs cho module Products Catalog và Purchasing & Receipts | Lan Anh | `a2d9ff6` | **MERGED & VERIFIED** |
| **#69** | `feature/backend-profile-product-api-enrichment` | — | Bổ sung API Profile người dùng và làm giàu dữ liệu Product Catalog phục vụ giao diện | Team | `e4a0363` | **MERGED & VERIFIED** |
| **#70** | `feature/T04AABC-qa-purchasing-email` | `T04AABC` | Kiểm thử chuyên sâu Purchasing Lifecycle và ràng buộc lưu trữ Outbox Events, cô lập Shared Admin | Na Na | `27371f5` | **MERGED & VERIFIED** |
| **#71** | `feature/T04AB25-dashboard-and-ai-ui` | `T04AB25` | Giao diện Dashboard quản trị thời gian thực, hiển thị chỉ số KPI và tích hợp UI trợ lý AI | Lâm | `45f1a5b` | **MERGED & VERIFIED** |
| **#72** | `feature/t3c9f30---night-mode` | `T3C9F30` | Chế độ ban đêm (Night Mode / Dark Theme), cô lập style CSS, loại bỏ rò rỉ nền trắng trên table/modal | Tân | `26ee520` | **MERGED & VERIFIED** |
| **#73** | `feature/T04A90F-outbox-email-worker` | `T04A90F` | Triển khai Celery Email Worker xử lý Transactional Outbox, cơ chế retry hàng đợi RabbitMQ | Hiếu | `00b6c56` | **MERGED & VERIFIED** |

---

### 2.2. Tổng Hợp Bằng Chứng Kiểm Thử & Độ Phủ Toàn Hệ Thống

#### 2.2.1. Thống kê kết quả kiểm thử tự động (Automated Test Execution Summary)

| Phân hệ / Bộ Kiểm thử | File Báo cáo / Test Suite | Số Test | Pass | Partial / Skip | Tỷ lệ Pass | Môi trường Thực thi & Bằng chứng |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| **Products & Purchasing (Lan Anh)** | `docs/sprint3/T3C9972_MODULE_TEST_CASES_AND_LOG.md` | **68** | 68 | 0 | **100%** | 53 unit/API test (runner local) + 15 MySQL integration test (GitHub Actions CI). |
| **Inventory & Confirmation (Dương)** | `docs/sprint3/testing/T3C9970/README.md` | **40** | 38 | 2 partial | **95.0%** | 38 Verified Pass; 2 Partial do boundary `expected_draft_version=1` trên phiếu đã đóng. |
| **Purchasing & Outbox QA (Na Na)** | `docs/sprint3/T04AABC_RECONCILIATION_REPORT.md` | **23+** | 23+ | 0 | **100%** | RBAC routes pass; kiểm chứng an toàn lưu trữ outbox và cô lập Shared Admin. |
| **Product, Order, Analytics (Na Na)** | `docs/sprint3/T04AAD7_RECONCILIATION_REPORT.md` | **18+** | 18+ | 0 | **100%** | Kiểm chứng Option A trên MySQL 8.4; cơ chế Run-scoped dọn dẹp độc lập. |
| **UI Dark Theme & Layout (Tân)** | `frontend/src/__tests__/` (PR #72) | **All** | All | 0 | **100%** | Kiểm chứng script chuyển đổi giao diện không gây xung đột style CSS. |
| **Code Style & Linting** | `ruff check .` & `ruff format --check .` | 180 files | 180 | 0 | **100%** | Đạt 100% quy chuẩn linter và định dạng mã nguồn. |

#### 2.2.2. Phân loại mức độ phủ và các điểm giới hạn (Coverage Gaps & Limitations):
- **Phần đã được kiểm chứng trực tiếp (Directly Covered):**
  - Nghiệp vụ Catalog: Tạo sản phẩm kèm kho 0 nguyên tử, chặn trùng SKU, DTO `ProductRead` che giấu hoàn toàn trường giá vốn đối với mọi role.
  - Nghiệp vụ Nhập hàng: Tạo phiếu nháp, tự động gộp dòng sản phẩm cùng giá (Item Merging), khóa lạc quan `draft_version`, hủy phiếu nháp giữ nguyên tồn kho, xác nhận phiếu nhập cộng tồn kho nguyên tử.
  - Nghiệp vụ Bán hàng & Kho: Bán hàng POS trừ kho nguyên tử, ghi nhận `StockMovement`, hủy đơn hàng hoàn tồn kho.
  - Nghiệp vụ Thống kê: Tính toán doanh thu, số đơn, AOV làm tròn chuẩn, thống kê sản phẩm bán chạy/chậm theo múi giờ Việt Nam.
- **Phần có giới hạn kiểm thử (Partially Covered / Pending Integration):**
  1. `TC-PROD-04`: Ràng buộc giá âm/bằng 0 được xác thực tại Pydantic Schema Validation (`test_products_schemas.py`), chưa có route client test riêng.
  2. `TC-PROD-11`: `GET /api/v1/products/{id}` đã có test 200 OK và đúng ID (`test_api_staff_can_read_but_gets_403_on_mutations`), nhưng chưa assert chi tiết toàn bộ 10 trường của `ProductRead`.
  3. `TC-PROD-15`: Xung đột trùng SKU khi cập nhật được kiểm thử tại tầng Service.
  4. `TC-PUR-08`: Chặn sửa phiếu non-DRAFT được kiểm thử tại tầng Service.
  5. `TC034`, `TC035` (`T3C9970`): Test xác nhận phiếu `CONFIRMED`/`CANCELLED` trả `409` qua cơ chế version cũ, chưa phủ nhánh mã lỗi `INVALID_STATE`.
  6. Email Worker Celery (`T04A90F`): Đã merge worker nền tảng; việc gửi email thực tế phụ thuộc vào cấu hình SMTP gateway thật, trong phạm vi test local/CI được xác thực thông qua hàng đợi và log sự kiện outbox.

---

### 2.3. Sổ Cái Theo Dõi Lỗi Hợp Nhất (Consolidated Defect Ledger)

Tổng hợp 14 lỗi kỹ thuật và sai lệch tài liệu đã được phát hiện, phân tích nguyên nhân gốc rễ và xử lý triệt để xuyên suốt các sprint:

| Defect ID | Phân Hệ / Task | Mức Độ | Triệu Chứng Lỗi & Nguyên Nhân Gốc Rễ | Giải Pháp Khắc Phục (Resolution) | Commit SHA Sửa Lỗi | Trạng Thái |
|:---:|:---:|:---:|:---|:---|:---:|:---:|
| **`DEF-001`** | Deploy / Docker (`T04A8D1`) | **Critical** | Không thể bind cổng `3306` khi chạy MySQL trên Windows do Hyper-V/WinNAT chiếm dụng cổng mặc định. | Cấu hình biến `MYSQL_HOST_PORT=13306` trong `.env.example`, cập nhật README và Runbook. | `b0d4dc9` | **DOCS_CORRECTED** |
| **`DEF-002`** | Purchasing (`T04A772`) | **High** | Lỗi `SQLAlchemy DetachedInstanceError` khi đọc thuộc tính `product` của `PurchaseReceiptItem` sau khi đóng session. | Bổ sung eager loading bằng cú pháp `joinedload(PurchaseReceipt.items).joinedload(PurchaseReceiptItem.product)`. | `546ae09` | **FIXED & VERIFIED** |
| **`DEF-003`** | Purchasing (`T04A772`) | **High** | Test hủy phiếu đồng thời thất bại do request thứ 2 không raise ngoại lệ `ConflictError(409)`. | So khớp chính xác điều kiện `draft_version == expected_draft_version` và trạng thái `DRAFT` trong câu lệnh cập nhật. | `546ae09` | **FIXED & VERIFIED** |
| **`DEF-004`** | CI Pipeline (`T04A689`) | **Medium** | Lỗi Ruff linter `F811 Redefinition of unused 'threading'` làm fail GitHub Actions CI. | Xóa bỏ dòng import thư viện dư thừa, định dạng lại mã nguồn bằng `ruff check --fix`. | `a8428f3` | **FIXED & VERIFIED** |
| **`DEF-005`** | Deploy / UAT (`T04A996`) | **Medium** | README cũ tham chiếu tới file không tồn tại `compose.local.yaml`, làm lệnh seed Admin báo lỗi file missing. | Chuẩn hóa lệnh seed sang `docker compose run --rm --no-deps backend python -m app.modules.auth.seed`. | `f1ced70` | **DOCS_CORRECTED** |
| **`DEF-006`** | Seed / Docs (`T04A996`) | **Low** | Thiếu hướng dẫn nạp dữ liệu hạt giống cho Categories và Suppliers trong quy trình Cold-Start. | Bổ sung đầy đủ lệnh nạp 5 categories và 3 suppliers vào Bước 3 của Cold-Start trong README và Runbook. | `f1ced70` | **DOCS_CORRECTED** |
| **`DEF-007`** | Docker / Network (`T04A996`) | **Medium** | Tài liệu cũ khẳng định Docker chặn toàn bộ truy cập MySQL, mâu thuẫn với cấu hình loopback `127.0.0.1:3306`. | Đính chính loopback binding an toàn cho máy host và lưu ý không dùng chung volume `mysql_data` khi chạy test CI. | `f1ced70` | **DOCS_CORRECTED** |
| **`DEF-008`** | API Contracts (`T04A996`) | **High** | Sai lệch hợp đồng API trong kịch bản UAT: query params `from_date`/`to_date` (thay vì `from`/`to`), lỗi out-of-stock ghi 400. | Rà soát toàn bộ 7 nhóm kịch bản theo `contracts/openapi.yaml`, đính chính 100% khớp với code implementation. | `f1ced70` | **DOCS_CORRECTED** |
| **`DEF-009`** | Products (`T3C9AEB`) | **High** | Xung đột chuỗi Alembic migration do khai báo trùng lặp Category model ở cả module products và categories. | Xóa bỏ Category model trùng lặp trong module products, chuẩn hóa import từ module categories. | `ee31bd0` | **FIXED & VERIFIED** |
| **`DEF-010`** | Products (`T3C9AEB`) | **Medium** | Teardown cleanup của test MySQL xóa nhầm các danh mục hạt giống có sẵn trong database. | Cô lập phạm vi cleanup chỉ xóa các ID sản phẩm được sinh ra trong fixture của chính bài test đó. | `1d60b93` | **FIXED & VERIFIED** |
| **`DEF-011`** | QA Isolation (`T04AAD7`) | **Medium** | Fixture autouse `clean_t04aad7_test_rows` xóa toàn bộ bản ghi có tiền tố `T04AAD7_%`, gây nguy cơ xóa chéo test khác. | Chuyển sang cơ chế Run-Scoped cleanup do `TestRunContext` quản lý, dọn dẹp theo dõi chặt chẽ danh sách ID thật. | `55ebc43` | **FIXED & VERIFIED** |
| **`DEF-012`** | Analytics QA (`T04AAD7`) | **Low** | Lệch ngày kiểm thử khi chạy qua mốc nửa đêm do lấy thời gian wall-clock độc lập giữa UTC và VN timezone. | Áp dụng Single Source of Truth cho thời gian: Khởi tạo một `frozen_time_utc` cố định và suy diễn ngày VN từ mốc đó. | `55ebc43` | **FIXED & VERIFIED** |
| **`DEF-013`** | Dashboard QA (`T04AA36`) | **Medium** | Lỗi check constraint `line_total_vnd` trong fixture bài test MySQL Dashboard do dữ liệu mock không khớp công thức. | Đồng bộ công thức `line_total_vnd = quantity * unit_price` trong fixture test MySQL. | `f3a7daf` | **FIXED & VERIFIED** |
| **`DEF-014`** | Frontend Theme (`T3C9F30`) | **Low** | Rò rỉ màu nền trắng trên table header và modal input khi người dùng kích hoạt Dark Theme (Night Mode). | Thiết lập biến màu CSS scoped, chuẩn hóa nền tối `#1e293b` và màu chữ trắng thuần `#f8fafc` trên toàn bộ component. | `26ee520` | **FIXED & VERIFIED** |

---

### 2.4. Đánh Giá Cổng Chất Lượng & Mức Độ Sẵn Sàng (Release Gate Assessment)

Phân định rõ ràng mức độ kiểm chứng theo 5 cấp độ chất lượng thực tế:

| Cấp Độ Kiểm Chứng | Hiện Trạng Thực Tế | Đánh Giá Cổng Chất Lượng |
|:---|:---|:---:|
| **1. Unit & Route API Tests** | Toàn bộ các test suite backend độc lập (`test_products_api.py`, `test_purchase_receipts_api.py`, `test_draft_service.py`, v.v.) đạt tỷ lệ 100% pass trên môi trường runner. | **PASSED** |
| **2. MySQL Integration Tests** | Đạt 100% pass trên môi trường CI GitHub Actions có container MySQL 8.4 InnoDB. Tại máy trạm không có DB container chuyên dụng, cơ chế `database_guard.py` kích hoạt fail-closed an toàn để tránh ô nhiễm DB development. | **PASSED (CI Verified)** |
| **3. Browser E2E Tests** | Chưa tích hợp bộ kiểm thử tự động toàn trình trình duyệt (Playwright/Cypress); hiện tại tính năng giao diện được kiểm chứng thông qua unit test component và quy trình kiểm thử thủ công (Manual UAT Protocol). | **PENDING E2E AUTOMATION**<br>*(Manual Verified)* |
| **4. Cold-Start & Deployment** | Cấu hình Docker Compose và 3 lệnh seed idempotent đã được đối soát thống nhất với `compose.yaml` và `README.md`. Cần kiểm tra thực tế (preflight check) trên máy trạm staging trước giờ demo. | **PARTIALLY VERIFIED**<br>*(Ready for Staging)* |
| **5. Manual UAT Acceptance** | Toàn bộ 24 kịch bản UAT đã được chuẩn bị đầy đủ; sẵn sàng cho phiên đánh giá nghiệm thu chính thức với hội đồng / khách hàng vào ngày **27/11/2026**. | **READY FOR DEMO / PENDING UAT SIGN-OFF** |

**Kết luận Release Gate:**
- **`GATE-E2E`:** **`PARTIALLY VERIFIED`** (Đạt ở cấp độ API & Database Integration; giao diện người dùng sẵn sàng cho kiểm chứng trực quan tại buổi demo).
- **`DEPLOY`:** **`PARTIALLY VERIFIED`** (Quy trình Docker Compose và biến môi trường đã được chuẩn hóa, sẵn sàng triển khai staging).
- **Trạng thái Task `T04ABDD`:** **`READY FOR LEAD REVIEW`** (Tài liệu phản ánh đúng hiện trạng kỹ thuật, không tự tuyên bố nghiệm thu khống).

---

## Phần II — Sổ Tay & Kịch Bản Trình Diễn Demo (Reproducible Demo Guide)

### 3.1. Checklist Tái Lập Môi Trường Chuẩn (Host & Docker Compose)

#### A. Yêu cầu Tiên quyết (Prerequisites):
- [ ] Cài đặt Docker Desktop (hỗ trợ Compose V2) hoặc Docker Engine trên máy tính demo.
- [ ] Xác định cổng lắng nghe Nginx: mặc định là cổng `80` (hoặc đặt `NGINX_HOST_PORT=8080` trong `.env` nếu cổng 80 bị chiếm dụng).
- [ ] Cổng MySQL host: mặc định đặt `MYSQL_HOST_PORT=13306` trong `.env` để tránh xung đột với cổng `3306` của Windows Hyper-V/WinNAT.
- [ ] File `.env` được tạo từ `.env.example` với các secret key tối thiểu 32 ký tự ngẫu nhiên.

#### B. Quy trình Khởi động Cold-Start 4 Bước Chuẩn:
> [!NOTE]
> **Kiến trúc dịch vụ trong `compose.yaml`:** Hệ thống gồm 4 service chính: `mysql`, `redis`, `backend` và `nginx`.
> Mã nguồn Frontend SPA (React + Vite) được biên dịch thông qua multi-stage build trong `docker/nginx/Dockerfile` và được phục vụ trực tiếp dưới dạng static assets bởi container `nginx`. Do đó, **không có service Compose độc lập tên `frontend`**.

Thực hiện tuần tự tại thư mục gốc của repository:

```powershell
# Bước 1: Build Docker images cho Backend và Nginx (tích hợp build static SPA)
docker compose build

# Bước 2: Khởi động dịch vụ cơ sở dữ liệu và cache, chờ đạt trạng thái healthy
docker compose up -d --wait mysql redis

# Bước 3: Chạy migration Alembic và nạp 3 bộ dữ liệu hạt giống idempotent
docker compose run --rm --no-deps backend alembic upgrade head
docker compose run --rm --no-deps -e RETAILOPS_ADMIN_SEED_EMAIL -e RETAILOPS_ADMIN_SEED_PASSWORD backend python -m app.modules.auth.seed
docker compose run --rm --no-deps backend python -m app.modules.categories.seed
docker compose run --rm --no-deps backend python -m app.modules.suppliers.seed

# Bước 4: Khởi động toàn bộ dịch vụ ứng dụng và kiểm tra trạng thái
docker compose up -d --wait
docker compose ps
```

#### C. Địa chỉ Truy cập & Lệnh Kiểm tra Sức khỏe Hệ thống (Health Check):
- **Giao diện Web (SPA qua Nginx):** `http://localhost:${NGINX_HOST_PORT:-80}/` (hoặc `http://127.0.0.1:${NGINX_HOST_PORT:-80}/`).
- **Tài liệu API tương tác (khi chạy local backend):** `http://127.0.0.1:${BACKEND_HOST_PORT:-8000}/docs`.
- **Lệnh kiểm tra sức khỏe API (sử dụng curl GET):**
  ```powershell
  # Trên Linux / macOS hoặc Git Bash:
  curl -fsS "http://127.0.0.1:${NGINX_HOST_PORT:-80}/api/v1/health"

  # Trên Windows PowerShell (sử dụng curl.exe trực tiếp để tránh alias):
  curl.exe -fsS "http://127.0.0.1:${env:NGINX_HOST_PORT:-80}/api/v1/health"
  # Phản hồi JSON kỳ vọng: {"status":"ok"}
  ```

---

### 3.2. Dữ Liệu Seed Nền Tảng & Quy Trình Chuẩn Bị Dữ Liệu Nghiệp Vụ Mẫu

#### 3.2.1. Dữ liệu hạt giống nền tảng (Foundation Seed Data — Đã tự động hóa)
Sau khi thực hiện Bước 3 của quy trình khởi động, hệ thống có sẵn:
1. **1 Tài khoản Quản trị viên (Admin):**
   - Email: Lấy từ `RETAILOPS_ADMIN_SEED_EMAIL` (giá trị mẫu development: `admin@retailops.local`).
   - Mật khẩu: Lấy từ `RETAILOPS_ADMIN_SEED_PASSWORD` (giá trị mẫu development: `AdminPassword@123`).
   - Vai trò: `ADMIN`, Trạng thái: `ACTIVE`, `admin_slot = 1`.
2. **5 Danh mục hàng hóa mặc định (Categories):**
   - Đồ uống, Bánh kẹo & Đồ ăn vặt, Thực phẩm đóng hộp, Hóa mỹ phẩm & Tẩy rửa, Đồ gia dụng tiện ích.
3. **3 Nhà cung cấp đối tác mẫu (Suppliers):**
   - Công ty TNHH Phân phối Nước giải khát Việt, Công ty Cổ phần Thực phẩm An Toàn, Đại lý Phân phối Hàng gia dụng Miền Bắc.

#### 3.2.2. Hướng dẫn chuẩn bị dữ liệu nghiệp vụ mẫu trước buổi Demo (Pre-Demo Provisioning)
> [!IMPORTANT]
> **Lưu ý về dữ liệu giao dịch:** Hệ thống **chưa có script seed tự động** cho Sản phẩm, Phiếu nhập và Đơn hàng để tránh sinh dữ liệu giả định. Để buổi demo diễn ra trơn tru, người phụ trách thực hiện tạo nhanh dữ liệu mẫu trước giờ thuyết trình theo 4 bước sau (mất khoảng 3 phút):

1. **Tạo tài khoản Nhân viên (Staff):**
   - Truy cập trang đăng ký `http://localhost:${NGINX_HOST_PORT:-80}/register`.
   - Tạo tài khoản mẫu: `staff@retailops.local` / `StaffPassword@123`.
   - Đăng nhập tài khoản `Admin`, mở menu **Quản lý Nhân sự**, duyệt tài khoản `staff@retailops.local`.
2. **Tạo 4 Sản phẩm mẫu trong Catalog (tìm kiếm theo SKU thay vì dựa vào ID cố định):**
   Đăng nhập tài khoản `Admin`, vào menu **Sản phẩm (Products)**, thêm mới:
   - SKU `DRK-COCA-330` — Tên: `Nước ngọt Coca Cola 330ml` — Danh mục: `Đồ uống` — Giá bán: `12,000 VND`.
   - SKU `DRK-MILK-TH1L` — Tên: `Sữa tươi tiệt trùng TH True Milk 1L` — Danh mục: `Đồ uống` — Giá bán: `38,000 VND`.
   - SKU `SNK-LAY-75G` — Tên: `Snack khoai tây Lay's vị tự nhiên 75g` — Danh mục: `Bánh kẹo & Đồ ăn vặt` — Giá bán: `20,000 VND`.
   - SKU `CAN-TUNA-185G` — Tên: `Cá ngừ ngâm dầu Hạ Long Can 185g` — Danh mục: `Thực phẩm đóng hộp` — Giá bán: `45,000 VND`.
   *(Hệ thống tự động sinh tồn kho `quantity = 0` cho mỗi sản phẩm mới).*
3. **Nhập hàng để tạo số dư kho (Purchasing Lifecycle):**
   - Vào menu **Nhập hàng (Purchasing)**, bấm **Tạo phiếu nhập nháp**:
     - Chọn Nhà cung cấp: `Công ty TNHH Phân phối Nước giải khát Việt`.
     - Thêm dòng 1: Sản phẩm `DRK-COCA-330`, Đơn giá nhập: `8,500 VND`, Số lượng: `100`.
     - Thêm dòng 2: Sản phẩm `DRK-MILK-TH1L`, Đơn giá nhập: `28,000 VND`, Số lượng: `50`.
     - Thêm dòng 3 (minh họa gộp dòng): Sản phẩm `DRK-COCA-330`, cùng đơn giá: `8,500 VND`, Số lượng: `20`.
   - Bấm **Lưu phiếu nháp** (phiếu chuyển sang `DRAFT`, `draft_version = 1`, 2 dòng Coca tự gộp thành số lượng 120, kho chưa tăng).
   - Bấm **Xác nhận nhập kho (Confirm Receipt)** -> Trạng thái phiếu chuyển `CONFIRMED`, tồn kho Coca tăng lên `120`, sữa TH tăng lên `50`.
4. **Tạo 1 đơn hàng mẫu qua POS:**
   - Đăng nhập tài khoản `Staff`, mở màn hình **Bán hàng (POS Checkout)**.
   - Chọn 2 lon Coca và 1 hộp sữa TH, bấm **Thanh toán**.
   - Giao dịch hoàn tất -> Tồn kho Coca trừ còn `118`, sữa TH trừ còn `49`. Dữ liệu sẵn sàng hiển thị trên Dashboard.

---

### 3.3. Kịch Bản Trình Diễn Chi Tiết & Phân Công Người Phụ Trách (6 Phân Cảnh)

**Thời lượng tổng thể:** 15 – 20 phút. Phân công 6 phân cảnh liền mạch:

```
[Scene 1: Auth & RBAC] ──> [Scene 2: Products & Data Masking] ──> [Scene 3: Purchasing & Optimistic Lock]
          │
          └──> [Scene 4: POS & Inventory] ──> [Scene 5: Dashboard & Analytics] ──> [Scene 6: Dark Mode & UX]
```

#### Phân cảnh 1: Xác Thực, Phân Quyền & Quy Trình Duyệt Nhân Viên (3 phút)
- **Người phụ trách:** **Vũ Hoàng Lan Anh** (Hỗ trợ kỹ thuật: Nguyễn Minh Hiếu)
- **Điều kiện chuẩn bị:** Hệ thống đã hoàn tất Cold-Start; tài khoản Admin đã đăng nhập trên trình duyệt chính.
- **Thao tác chính:**
  1. Mở cửa sổ ẩn danh, đăng ký nhân viên mới `staff2@retailops.local`. Thử đăng nhập ngay -> Hệ thống hiển thị thông báo tài khoản đang chờ phê duyệt (`PENDING_APPROVAL`) và chặn truy cập tài nguyên nghiệp vụ.
  2. Mở trình duyệt Admin, vào trang **Quản lý Nhân sự**, bấm **Phê duyệt (Approve)** cho `staff2@retailops.local`.
  3. Quay lại cửa sổ ẩn danh, đăng nhập lại -> Đăng nhập thành công, nhận cookie session `HttpOnly` an toàn.
- **Kết quả kỳ vọng:** Chứng minh cơ chế bảo vệ Admin duy nhất (`admin_slot = 1`), luồng duyệt nhân sự 2 bước chống spam và cookie xác thực an toàn.
- **Phương án dự phòng:** Nếu tài khoản đăng ký không hiển thị ngay, Admin bấm nút Refresh trên bảng duyệt nhân viên để nạp lại danh sách.

#### Phân cảnh 2: Quản Lý Sản Phẩm & Bảo Mật Dữ Liệu Giá Vốn (3 phút)
- **Người phụ trách:** **Vũ Hoàng Lan Anh** (Phối hợp: Phạm Nhật Tân)
- **Điều kiện chuẩn bị:** 4 sản phẩm mẫu đã được tạo ở bước chuẩn bị.
- **Thao tác chính:**
  1. Tài khoản `Admin`: Vào danh mục sản phẩm, tìm kiếm theo tên hoặc SKU `DRK-COCA-330`, cập nhật giá bán. Thử đổi sang một SKU đã có sẵn -> Hệ thống từ chối với lỗi HTTP `409 Conflict (DUPLICATE_SKU)`.
  2. Tài khoản `Staff`: Vào danh mục sản phẩm, mở công cụ Network DevTools của trình duyệt để soi response `GET /api/v1/products`.
  3. Khẳng định trong response DTO `ProductRead`, **hoàn toàn không có trường giá vốn nào** (`cost_price_vnd`, `unit_cost_vnd`, hay `cost`) trả về cho Staff.
  4. Staff thử bấm sửa sản phẩm -> Giao diện vô hiệu hóa nút sửa và backend chặn với HTTP `403 Forbidden`.
- **Kết quả kỳ vọng:** Ràng buộc duy nhất của SKU, tính nguyên tử khi tạo sản phẩm kèm kho 0, và nguyên tắc bảo mật thông tin giá vốn kinh doanh trước nhân viên thu ngân.
- **Phương án dự phòng:** Nếu trình duyệt không mở được DevTools, người thuyết trình chỉ trực tiếp trên UI Staff không hề có cột "Giá vốn".

#### Phân cảnh 3: Quản Lý Nhập Hàng & Khóa Lạc Quan (4 phút)
- **Người phụ trách:** **Vũ Hoàng Lan Anh** (Phối hợp: Na Na)
- **Điều kiện chuẩn bị:** Đăng nhập tài khoản `Admin` (module Purchasing chỉ dành riêng cho Admin).
- **Thao tác chính:**
  1. Tạo phiếu nhập nháp: Thêm 2 dòng cùng 1 sản phẩm và cùng đơn giá -> Hệ thống tự động gộp dòng thành 1 dòng duy nhất (Item Merging).
  2. Thử thêm 2 dòng cùng sản phẩm nhưng khác đơn giá -> Hệ thống báo lỗi xung đột đơn giá `HTTP 422 (COST_CONFLICT)`.
  3. Minh họa **Khóa lạc quan (Optimistic Locking):** Mở cùng 1 phiếu nháp trên 2 tab trình duyệt (cùng `draft_version = 1`). Tab 1 bấm lưu -> Thành công, version tăng lên 2. Tab 2 bấm lưu -> Báo lỗi xung đột phiên bản `HTTP 409 Conflict (RECEIPT_VERSION_CONFLICT)`, ngăn chặn Lost-Update.
  4. Thao tác hủy phiếu nháp: Trạng thái chuyển sang `CANCELLED`, tồn kho trong bảng `inventories` hoàn toàn không bị thay đổi.
  5. Xác nhận phiếu nhập hợp lệ: Bấm **Xác nhận (Confirm)** -> Trạng thái chuyển sang `CONFIRMED`, tồn kho tự động cộng dồn nguyên tử.
- **Kết quả kỳ vọng:** Khóa lạc quan chống race condition và phân định rõ ràng: **Hủy phiếu nháp** là hủy ý định nhập hàng (không đổi kho), khác với **Hủy đơn hàng** ở phân cảnh 4.
- **Phương án dự phòng:** Nếu tab 2 không hiển thị popup xung đột, kiểm tra mã lỗi HTTP 409 trong tab Console/Network.

#### Phân cảnh 4: Bán Hàng Thu Ngân (POS) & Hủy Đơn Hoàn Kho (3 phút)
- **Người phụ trách:** **Nguyễn Cao Lâm** (Phối hợp: Cao Nguyễn Anh Dương)
- **Điều kiện chuẩn bị:** Đăng nhập tài khoản `Staff` (Thu ngân); sản phẩm đã có số dư tồn kho từ phân cảnh 3.
- **Thao tác chính:**
  1. Mở màn hình **POS Thu Ngân**: Chọn sản phẩm Coca và Sữa TH. Thử nhập số lượng vượt quá tồn kho khả dụng -> Giao diện cảnh báo vượt tồn kho.
  2. Bấm **Thanh toán**: Đơn hàng tạo thành công, tồn kho lập tức bị trừ tương ứng trong cơ sở dữ liệu.
  3. Mở tab **Lịch sử đơn hàng (Order History)**: Tìm đơn hàng vừa tạo, bấm **Hủy đơn hàng (Order Cancellation)**.
  4. Mở lại màn hình Quản lý kho: Chứng minh số lượng tồn kho được hoàn trả chính xác về kho và ghi nhận bản ghi `StockMovement` (kind `ORDER_CANCEL`).
- **Kết quả kỳ vọng:** Quy trình bán hàng POS mượt mà, phân trang 12/10 sản phẩm tối ưu cảm ứng; giao dịch thanh toán và hủy đơn đảm bảo tính toàn vẹn kho hàng (ACID).
- **Phương án dự phòng:** Nếu gặp lỗi quyền hạn khi hủy đơn, đảm bảo hủy bằng chính tài khoản Staff đã tạo đơn đó (theo đúng quy tắc ownership của `OrderService`).

#### Phân cảnh 5: Dashboard Quản Trị & Báo Cáo Phân Tích (4 phút)
- **Người phụ trách:** **Na Na** (Phối hợp: Cao Nguyễn Anh Dương)
- **Điều kiện chuẩn bị:** Tài khoản `Admin` đã đăng nhập; hệ thống đã có phát sinh đơn hàng từ phân cảnh 4.
- **Thao tác chính:**
  1. Mở màn hình **Dashboard Quản Trị**: Trình bày các thẻ KPI thời gian thực gồm Tổng doanh thu, Số đơn hoàn thành, Giá trị trung bình đơn (AOV) và Cảnh báo hàng sắp hết (Low Stock Warning).
  2. Chuyển sang màn hình **Phân tích Doanh thu (Sales Analytics)**: Lọc theo khoảng ngày Việt Nam (UTC+7), minh họa biểu đồ doanh thu theo ngày.
  3. Trình chiếu bảng **Sản phẩm bán chạy nhất (Top Selling Products)** và **Sản phẩm bán chậm (Slow Moving Products)**: Chứng minh thuật toán gom nhóm đúng theo `product_id` ngay cả khi sản phẩm đã được đổi tên trong catalog.
- **Kết quả kỳ vọng:** Số liệu Dashboard đồng bộ số học với Sales Analytics; xử lý chuẩn múi giờ Việt Nam theo khoảng nửa mở `[00:00:00, 24:00:00)`.
- **Phương án dự phòng:** Nếu biểu đồ chưa cập nhật do cache, bấm nút Refresh hoặc đổi lại bộ lọc ngày để kích hoạt truy vấn mới.

#### Phân cảnh 6: Giao Diện Dark Mode (Night Mode) & Responsive UX (3 phút)
- **Người phụ trách:** **Phạm Nhật Tân**
- **Điều kiện chuẩn bị:** Đang ở giao diện ứng dụng trên màn hình bất kỳ.
- **Thao tác chính:**
  1. Tại thanh Header điều hướng, bấm nút chuyển đổi giao diện **Chế độ Sáng / Tối (Light / Dark Theme Toggle)** bên cạnh nút Trợ giúp.
  2. Chuyển đổi qua lại giữa Light Mode và Dark Mode trên các màn hình phức tạp: Dashboard biểu đồ, Bảng danh mục sản phẩm, Bảng nhập hàng và Modal pop-up.
  3. Thu nhỏ kích thước cửa sổ trình duyệt để minh họa tính năng **Responsive Layout** trên kích thước máy tính bảng và điện thoại di động.
- **Kết quả kỳ vọng:** Dark Mode bảo vệ mắt chuyên nghiệp, không bị rò rỉ nền trắng trên table header hay form inputs (đã giải quyết triệt để lỗi `DEF-014`).
- **Phương án dự phòng:** Nếu giao diện không đổi màu, kiểm tra thuộc tính `data-theme` trên thẻ `<html>` hoặc xóa cache `localStorage`.

---

### 3.4. Giới Hạn Đã Biết & Kịch Bản Dự Phòng Rủi Ro (Fallback Plan)

| Tình Huống Sự Cố | Nguyên Nhân Kỹ Thuật | Phương Án Xử Lý Tức Thì (Fallback Plan) |
|:---|:---|:---|
| **Lỗi bind cổng `3306` khi bật Docker** | Dịch vụ MySQL cục bộ hoặc Hyper-V trên Windows chiếm cổng `3306`. | Sử dụng cấu hình thay thế đã chuẩn bị: đổi `MYSQL_HOST_PORT=13306` trong file `.env` và kết nối qua cổng `13306`. |
| **Giao diện báo lỗi `HTTP 500` sau khi bật Docker** | Nginx đã mở traffic nhưng container Backend chưa hoàn tất migration schema. | Tuân thủ quy trình Cold-Start: chạy lệnh `docker compose run --rm --no-deps backend alembic upgrade head` trước khi truy cập web. |
| **Chạy test MySQL báo lỗi fail-closed `database_guard`** | Biến môi trường test database chuyên dụng (`RETAILOPS_TEST_DATABASE_URL`) chưa có trên host. | Đây là cơ chế an toàn bảo vệ database development. Để chạy test tích hợp, khởi chạy stack overlay: `docker compose -f compose.yaml -f compose.ci.yaml up -d`. |
| **Dữ liệu demo bị thiếu hoặc người dùng bấm nhầm** | Thao tác sai hoặc chưa hoàn thành bước chuẩn bị dữ liệu mẫu. | Khôi phục trong 30 giây: chạy lại 3 lệnh seed idempotent (`auth`, `categories`, `suppliers`) mà không cần xóa volume, sau đó tạo nhanh lại sản phẩm mẫu theo Mục 3.2.2. |
| **Mất kết nối Internet trong buổi thuyết trình** | Sự cố mạng WiFi hội trường. | Toàn bộ hệ thống RetailOps chạy cục bộ 100% trong Docker trên máy trạm (`localhost`), không phụ thuộc vào Internet. Buổi demo tiếp tục bình thường. |
| **Câu hỏi về gửi email thực tế từ hệ thống** | Celery Worker (`T04A90F`) xử lý hàng đợi background. | Trả lời rõ: Hệ thống đã hoàn thiện mô hình Transactional Outbox (lưu sự kiện vào bảng `outbox_events` nguyên tử cùng transaction). Việc chuyển phát email qua SMTP phụ thuộc vào hạ tầng mail server ngoài, trong phạm vi demo nhóm chứng minh sự kiện outbox đã được ghi nhận an toàn trong database. |

---

> [!NOTE]
> **Kết luận Bàn giao Task T04ABDD:** Bản tài liệu QA Report và Demo Playbook này là sản phẩm chính thức của task `T04ABDD`, phản ánh trung thực kết quả kiểm thử toàn hệ thống và cung cấp quy trình trình diễn chuẩn xác phục vụ trực tiếp cho buổi nghiệm thu release ngày **27/11/2026**.
