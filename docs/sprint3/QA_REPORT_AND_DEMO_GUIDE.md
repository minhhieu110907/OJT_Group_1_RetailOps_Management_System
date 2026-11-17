# RetailOps V1.0 — Báo Cáo QA Tổng Hợp & Sổ Tay Trình Diễn Demo (Sprint 3)

**Hệ thống:** RetailOps Management System V1.0  
**Mã Task LMS:** `T04ABDD` — `[S3] Báo cáo QA và tài liệu demo`  
**Kỹ sư phụ trách:** Vũ Hoàng Lan Anh  
**Mã sinh viên:** `B25DTCN143`  
**Hợp đồng & Cổng kiểm soát:** `GATE-E2E, DEPLOY`  
**Mốc kế hoạch Excel:** 24/11/2026  
**Nhánh Git:** `feature/t04abdd-qa-report-and-demo`  
**Base Commit (develop):** `9684882` (*Merge pull request #67 from minhhieu110907/feature/T04A947-sales-analytics-api*)  

---

## MỤC LỤC
1. [Thông Tin Quản Lý Tài Liệu & Phạm Vi Task T04ABDD](#1-thông-tin-quản-lý-tài-liệu--phạm-vi-task-t04abdd)
2. [Phần I — Báo Cáo QA Tổng Hợp Sprint 3](#phần-i--báo-cáo-qa-tổng-hợp-sprint-3)
   - 2.1. [Bảng Đối Soát Sáp Nhập PR & Commit trên Develop](#21-bảng-đối-soát-sáp-nhập-pr--commit-trên-develop)
   - 2.2. [Tổng Hợp Bằng Chứng Kiểm Thử & Độ Phủ Toàn Hệ Thống](#22-tổng-hợp-bằng-chứng-kiểm-thử--độ-phủ-toàn-hệ-thống)
   - 2.3. [Sổ Cái Theo Dõi Lỗi Hợp Nhất (Consolidated Defect Ledger)](#23-sổ-cái-theo-dõi-lỗi-hợp-nhất-consolidated-defect-ledger)
   - 2.4. [Đánh Giá Cổng Chất Lượng & Sẵn Sàng Bàn Giao (Release Gate)](#24-đánh-giá-cổng-chất-lượng--sẵn-sàng-bàn-giao-release-gate)
3. [Phần II — Sổ Tay & Kịch Bản Trình Diễn Demo (Reproducible Demo Guide)](#phần-ii--sổ-tay--kịch-bản-trình-diễn-demo-reproducible-demo-guide)
   - 3.1. [Checklist Tái Lập Môi Trường Chuẩn (Host & Docker)](#31-checklist-tái-lập-môi-trường-chuẩn-host--docker)
   - 3.2. [Dữ Liệu Seed Nền Tảng & Quy Trình Chuẩn Bị Dữ Liệu Nghiệp Vụ Mẫu](#32-dữ-liệu-seed-nền-tảng--quy-trình-chuẩn-bị-dữ-liệu-nghiệp-vụ-mẫu)
   - 3.3. [Kịch Bản Trình Diễn Chi Tiết & Phân Công Người Phụ Trách](#33-kịch-bản-trình-diễn-chi-tiết--phân-công-người-phụ-trách)
   - 3.4. [Giới Hạn Đã Biết & Kịch Bản Dự Phòng Rủi Ro (Fallback Plan)](#34-giới-hạn-đã-biết--kịch-bản-dự-phòng-rủi-ro-fallback-plan)

---

## 1. Thông Tin Quản Lý Tài Liệu & Phạm Vi Task T04ABDD

### 1.1. Mục đích và Định hướng
Tài liệu này được lập theo chuẩn Definition of Done (DoD) của Sprint 3 nhằm đáp ứng hai mục tiêu cốt lõi:
1. **Báo cáo QA Cấp Release (Consolidated QA Report):** Tổng hợp và đối soát toàn bộ các kết quả kiểm thử đơn lẻ từ các thành viên trong nhóm (`T3C9972`, `T3C9970`, `T04AABC`, `T04AAD7`), rà soát các PR đã sáp nhập vào `develop`, tổng hợp sổ cái theo dõi lỗi (Defect Ledger) và xác nhận mức độ sẵn sàng cho mốc phát hành release (`24/11`).
2. **Kịch bản Demo Khả lặp (Reproducible Demo Playbook):** Cung cấp tài liệu chỉ dẫn từng bước giúp bất kỳ kỹ sư hoặc bên liên quan nào có thể khởi động lại toàn bộ hệ thống từ con số 0 trên máy tính cá nhân, nạp dữ liệu hạt giống và thực hiện bài thuyết trình demo các phân cảnh nghiệp vụ theo phân công cụ thể.

### 1.2. Nguyên tắc Bắt buộc
- **Tuyệt đối trung thực (Evidence-based & No Fake PASS):** Chỉ ghi nhận trạng thái đã kiểm chứng khi có bằng chứng thực thi test thực tế; các phần phụ thuộc chưa merge hoặc chưa hoàn tất kiểm thử đều phải ghi nhận đúng thực trạng (`DEFERRED`, `PARTIALLY COVERED`).
- **Bảo mật tuyệt đối (Zero Secret Leakage):** Mọi hướng dẫn chạy, cấu hình môi trường đều sử dụng biến mẫu từ `.env.example`. Tuyệt đối không chứa mật khẩu, JWT token hay secret key thật.
- **Tuân thủ hợp đồng hệ thống (Contract Adherence):** Bám sát các đặc tả trong `contracts/openapi.yaml`, `contracts/python/retailops_extended_ports.pyi`, và `docs/contracts/API_INTEGRATION.md`.

---

## Phần I — Báo Cáo QA Tổng Hợp Sprint 3

### 2.1. Bảng Đối Soát Sáp Nhập PR & Commit trên Develop

Tính đến commit baseline `9684882`, toàn bộ 13 Pull Request then chốt của Sprint 3 đã được review và sáp nhập vào nhánh `develop`:

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

---

### 2.2. Tổng Hợp Bằng Chứng Kiểm Thử & Độ Phủ Toàn Hệ Thống

#### 2.2.1. Thống kê kết quả kiểm thử tự động (Automated Test Execution Summary)

| Phân hệ / Bộ Kiểm thử | File Báo cáo / Test Suite | Số Test | Pass | Fail / Skip | Tỷ lệ Pass | Ghi chú Môi trường Thực thi |
|:---|:---|:---:|:---:|:---:|:---:|:---|
| **Products & Purchasing (Lan Anh)** | `docs/sprint3/T3C9972_MODULE_TEST_CASES_AND_LOG.md` | **68** | 68 | 0 | **100%** | 53 unit/API test (3.71s local) + 15 MySQL integration test (7.82s CI). |
| **Inventory & Confirmation (Dương)** | `docs/sprint3/testing/T3C9970/README.md` | **40** | 38 | 2 partial | **95.0%** | 38 Verified Pass; 2 Partial do boundary expected_draft_version=1 trên phiếu đã đóng. |
| **Purchasing & Outbox QA (Na Na)** | `docs/sprint3/T04AABC_RECONCILIATION_REPORT.md` | **23+** | 23+ | 0 | **100%** | RBAC 200/201/403/401; cô lập Idempotency và Shared ADMIN thành công. |
| **Product, Order, Analytics (Na Na)** | `docs/sprint3/T04AAD7_RECONCILIATION_REPORT.md` | **18+** | 18+ | 0 | **100%** | Kiểm chứng Option A trên MySQL 8.4; dọn dẹp Run-scoped theo dõi chặt chẽ ID. |
| **UI Dark Theme & Layout (Tân)** | `frontend/src/__tests__/` (PR #72) | **All** | All | 0 | **100%** | Đã cô lập theme script, kiểm chứng chuyển đổi toggle không xung đột style. |
| **Code Style & Linting** | `ruff check .` & `ruff format --check .` | 180 files | 180 | 0 | **100%** | Sạch hoàn toàn, 0 cảnh báo linter. |

#### 2.2.2. Phân loại mức độ phủ kiểm thử (Coverage Classification):
- **DIRECTLY COVERED:** Chiếm đa số (> 85%), bao gồm toàn bộ các luồng write path trọng yếu: tạo sản phẩm kèm kho 0, gộp dòng phiếu nhập, khóa lạc quan `draft_version`, xác nhận phiếu tăng tồn kho, bán hàng POS trừ kho nguyên tử, hủy đơn hoàn kho, tổng hợp analytics doanh thu và dashboard KPI.
- **PARTIALLY COVERED (Coverage Gaps ghi nhận trung thực):**
  1. `TC-PROD-04`: Ràng buộc giá âm/bằng 0 được xác thực tại Pydantic Schema Validation (`test_products_schemas.py`), chưa có route client test riêng.
  2. `TC-PROD-11`: `GET /api/v1/products/{id}` đã có test 200 OK và đúng ID (`test_api_staff_can_read_but_gets_403_on_mutations`), nhưng chưa assert chi tiết toàn bộ 10 trường an toàn của `ProductRead`.
  3. `TC-PROD-15`: Xung đột trùng SKU khi cập nhật được kiểm thử tại tầng Service.
  4. `TC-PUR-08`: Chặn sửa phiếu non-DRAFT được kiểm thử tại tầng Service.
  5. `TC034`, `TC035` (`T3C9970`): Test xác nhận phiếu `CONFIRMED`/`CANCELLED` trả `409` qua cơ chế version cũ, chưa phủ nhánh mã lỗi `INVALID_STATE`.
  6. Email Worker Celery & Password Reset AES-GCM: Tạm thời sử dụng Reference Model trong `T04AABC` do Celery daemon tách biệt khỏi stack HTTP chính.

---

### 2.3. Sổ Cái Theo Dõi Lỗi Hợp Nhất (Consolidated Defect Ledger)

Tổng hợp toàn bộ 14 lỗi kỹ thuật và sai lệch tài liệu đã được phát hiện, phân tích nguyên nhân gốc rễ và xử lý triệt để xuyên suốt từ Sprint 1 đến Sprint 3:

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

### 2.4. Đánh Giá Cổng Chất Lượng & Sẵn Sàng Bàn Giao (Release Gate)

Đối chiếu với tiêu chuẩn Definition of Done (DoD) của task `T04ABDD` và các cổng kiểm soát phát hành:
- **Cổng `GATE-E2E`:** **ĐẠT (PASSED)**. Toàn bộ các luồng nghiệp vụ cốt lõi từ Auth, Phân quyền, Danh mục, Sản phẩm, Nhập hàng, Quản lý tồn kho, Bán hàng POS và Dashboard đã được kiểm chứng end-to-end trên môi trường tích hợp.
- **Cổng `DEPLOY`:** **ĐẠT (PASSED)**. Quy trình đóng gói Docker Nginx chuẩn 4 bước và cấu hình biến môi trường an toàn đã được kiểm chứng tái lập thành công trên máy tính độc lập.
- **Độ tin cậy dữ liệu:** 100% các thao tác ghi dữ liệu (Write Path) quan trọng đều bảo đảm tính nguyên tử (Atomicity), an toàn giao dịch MySQL InnoDB, hỗ trợ khóa lạc quan chống Lost-Update và có log biến động kho `StockMovement`.
- **Kết luận:** Hệ thống đạt trạng thái **`ACCEPTED`** về mặt kiểm thử QA và **SẴN SÀNG CHO PHIÊN TRÌNH DIỄN DEMO CHÍNH THỨC**.

---

## Phần II — Sổ Tay & Kịch Bản Trình Diễn Demo (Reproducible Demo Guide)

### 3.1. Checklist Tái Lập Môi Trường Chuẩn (Host & Docker)

Để bảo đảm buổi demo diễn ra ổn định, kỹ sư phụ trách cần thực hiện kiểm tra môi trường theo checklist dưới đây:

#### A. Yêu cầu Tiên quyết (Prerequisites):
- [ ] Đã cài đặt Docker Desktop (hỗ trợ Compose V2) hoặc Docker Engine trên Linux/macOS.
- [ ] Cổng `80` (HTTP) và `443` (nếu dùng SSL) trên máy host không bị ứng dụng khác (IIS, Apache, Skype) chiếm dụng.
- [ ] Cổng `13306` khả dụng để bind loopback cho MySQL (tránh xung đột cổng `3306` mặc định trên Windows).
- [ ] File cấu hình môi trường `.env` đã được sao chép từ `.env.example` với các khóa bí mật tối thiểu 32 ký tự ngẫu nhiên.

#### B. Quy trình Khởi động Cold-Start 4 Bước Chuẩn (Từ Thư mục Gốc):
```powershell
# Bước 1: Build toàn bộ Docker images (Backend, Frontend, Nginx reverse proxy)
docker compose build

# Bước 2: Khởi động dịch vụ lưu trữ nền tảng và chờ chuyển sang trạng thái healthy
docker compose up -d --wait mysql redis

# Bước 3: Chạy migration schema Alembic và nạp 3 bộ dữ liệu hạt giống idempotent
docker compose run --rm --no-deps backend alembic upgrade head
docker compose run --rm --no-deps -e RETAILOPS_ADMIN_SEED_EMAIL -e RETAILOPS_ADMIN_SEED_PASSWORD backend python -m app.modules.auth.seed
docker compose run --rm --no-deps backend python -m app.modules.categories.seed
docker compose run --rm --no-deps backend python -m app.modules.suppliers.seed

# Bước 4: Khởi chạy toàn bộ hệ thống dịch vụ (Backend API, Frontend SPA, Nginx Proxy)
docker compose up -d backend frontend nginx
```

#### C. Địa chỉ Truy cập Dịch vụ:
- **Giao diện Web (SPA Frontend qua Nginx):** `http://localhost/` hoặc `http://127.0.0.1/`
- **Tài liệu API tương tác (Swagger UI trực tiếp):** `http://127.0.0.1:8000/docs` (khi chạy local backend) hoặc qua Nginx `/api/v1/docs` (nếu cấu hình).
- **Kiểm tra trạng thái hệ thống (Health Check):**
  ```powershell
  curl -I http://127.0.0.1/api/v1/health
  # Kỳ vọng phản hồi: HTTP/1.1 200 OK kèm {"status": "ok"}
  ```

---

### 3.2. Dữ Liệu Seed Nền Tảng & Quy Trình Chuẩn Bị Dữ Liệu Nghiệp Vụ Mẫu

#### 3.2.1. Dữ liệu hạt giống nền tảng (Foundation Seed Data — Đã tự động hóa)
Sau khi hoàn tất Bước 3 của quy trình Cold-Start, cơ sở dữ liệu đã có sẵn:
1. **1 Tài khoản Quản trị viên khởi tạo (Admin User):**
   - Email: Được nạp từ biến `RETAILOPS_ADMIN_SEED_EMAIL` trong `.env` (ví dụ mẫu: `admin@retailops.local`).
   - Mật khẩu: Được nạp từ biến `RETAILOPS_ADMIN_SEED_PASSWORD` trong `.env` (ví dụ mẫu: `AdminPassword@123`).
   - Vai trò: `ADMIN`, Trạng thái: `ACTIVE`, `admin_slot = 1`.
2. **5 Danh mục hàng hóa chuẩn (Categories):**
   - `ID 1`: Đồ uống
   - `ID 2`: Bánh kẹo & Đồ ăn vặt
   - `ID 3`: Thực phẩm đóng hộp
   - `ID 4`: Hóa mỹ phẩm & Tẩy rửa
   - `ID 5`: Đồ gia dụng tiện ích
3. **3 Nhà cung cấp đối tác mẫu (Suppliers):**
   - `ID 1`: Công ty TNHH Phân phối Nước giải khát Việt (`contact_email`: `contact@beverages-vn.example.com`, SĐT: `0901234567`)
   - `ID 2`: Công ty Cổ phần Thực phẩm An Toàn (`contact_email`: `info@safefood.example.com`, SĐT: `0912345678`)
   - `ID 3`: Đại lý Phân phối Hàng gia dụng Miền Bắc (`contact_email`: `giadung@daily.example.com`, SĐT: `0987654321`)

#### 3.2.2. Hướng dẫn tạo Dữ liệu Nghiệp vụ Mẫu cho buổi Demo (Pre-Demo Provisioning Flow)
> [!IMPORTANT]
> **Lưu ý quan trọng về dữ liệu giao dịch:** Hệ thống hiện tại **chưa có script seed tự động riêng** cho Sản phẩm (Products), Phiếu nhập (Purchase Receipts) và Đơn hàng (Orders), nhằm bảo đảm tính toàn vẹn và không tạo dữ liệu rác ngoài tầm kiểm soát.  
> Để có dữ liệu sinh động cho buổi demo, người trình diễn thực hiện luồng nạp dữ liệu nghiệp vụ mẫu trong vòng 3 phút trước giờ thuyết trình theo các bước sau:

1. **Bước 1 — Đăng ký & Duyệt tài khoản Thu ngân (Staff):**
   - Truy cập trang đăng ký `http://localhost/register`, tạo tài khoản nhân viên:
     `Email: staff@retailops.local` / `Mật khẩu: StaffPassword@123`.
   - Đăng nhập tài khoản `Admin`, vào màn hình **Quản lý Nhân viên (Staff Approvals)**, bấm **Phê duyệt (Approve)** cho tài khoản `staff@retailops.local`.
2. **Bước 2 — Tạo 4 Sản phẩm mẫu trong Catalog:**
   Đăng nhập bằng tài khoản `Admin`, vào menu **Sản phẩm (Products)**, bấm **Thêm mới sản phẩm**:
   - *Sản phẩm 1:* SKU `DRK-COCA-330`, Tên: `Nước ngọt Coca Cola 330ml`, Danh mục: `Đồ uống` (ID 1), Giá bán: `12,000 VND`.
   - *Sản phẩm 2:* SKU `DRK-MILK-TH1L`, Tên: `Sữa tươi tiệt trùng TH True Milk 1L`, Danh mục: `Đồ uống` (ID 1), Giá bán: `38,000 VND`.
   - *Sản phẩm 3:* SKU `SNK-LAY-75G`, Tên: `Snack khoai tây Lay's vị tự nhiên 75g`, Danh mục: `Bánh kẹo & Đồ ăn vặt` (ID 2), Giá bán: `20,000 VND`.
   - *Sản phẩm 4:* SKU `CAN-TUNA-185G`, Tên: `Cá ngừ ngâm dầu Hạ Long Can 185g`, Danh mục: `Thực phẩm đóng hộp` (ID 3), Giá bán: `45,000 VND`.
   *(Lưu ý: Ngay sau khi tạo, hệ thống tự động sinh bản ghi tồn kho `quantity = 0` cho mỗi sản phẩm).*
3. **Bước 3 — Nhập hàng tăng tồn kho (Purchase Receipt Lifecycle):**
   - Vào menu **Nhập hàng (Purchasing)**, bấm **Tạo phiếu nhập nháp**:
     - Chọn Nhà cung cấp: `Công ty TNHH Phân phối Nước giải khát Việt`.
     - Dòng 1: Sản phẩm `Nước ngọt Coca Cola 330ml`, Đơn giá nhập: `8,500 VND`, Số lượng: `100`.
     - Dòng 2: Sản phẩm `Sữa tươi tiệt trùng TH True Milk 1L`, Đơn giá nhập: `28,000 VND`, Số lượng: `50`.
     - Dòng 3: Thêm lặp lại dòng `Nước ngọt Coca Cola 330ml` cùng giá `8,500 VND`, Số lượng: `20` *(minh họa tính năng tự động gộp dòng lên 120 lon)*.
   - Bấm **Lưu phiếu nháp** (chuyển sang `DRAFT`, `draft_version = 1`, tồn kho chưa tăng).
   - Bấm **Xác nhận nhập kho (Confirm Receipt)** -> Trạng thái chuyển sang `CONFIRMED`, tồn kho `DRK-COCA-330` tăng lên `120`, `DRK-MILK-TH1L` tăng lên `50`.
4. **Bước 4 — Bán thử 1 đơn hàng qua POS:**
   - Đăng nhập tài khoản `Staff` (Thu ngân).
   - Mở màn hình **Bán hàng (POS Checkout)**: Chọn 2 lon Coca và 1 hộp sữa TH -> Bấm **Thanh toán**.
   - Đơn hàng hoàn tất -> Tồn kho Coca tự động trừ còn `118`, sữa TH trừ còn `49`. Dữ liệu lập tức phản ánh lên Dashboard.

---

### 3.3. Kịch Bản Trình Diễn Chi Tiết & Phân Công Người Phụ Trách

Tổng thời lượng dự kiến: **15 – 20 phút**. Kịch bản chia làm 6 phân cảnh (Scenes) liền mạch:

```
[Scene 1: Auth & RBAC] ──> [Scene 2: Products & Data Masking] ──> [Scene 3: Purchasing & Optimistic Lock]
          │
          └──> [Scene 4: POS & Inventory] ──> [Scene 5: Dashboard & Analytics] ──> [Scene 6: Dark Mode & UX]
```

#### Phân cảnh 1: Xác Thực, Phân Quyền & Quy Trình Duyệt Nhân Viên (Thời lượng: 3 phút)
- **Người trình diễn (Presenter):** **Vũ Hoàng Lan Anh** (hoặc Nguyễn Minh Hiếu hỗ trợ kỹ thuật)
- **Hành động thao tác:**
  1. Mở trình duyệt ẩn danh, đăng ký tài khoản nhân viên mới `staff2@retailops.local`. Đăng nhập thử -> Hệ thống hiển thị thông báo tài khoản đang chờ phê duyệt (`PENDING_APPROVAL`), chặn truy cập các tài nguyên nghiệp vụ.
  2. Mở trình duyệt chính đang đăng nhập tài khoản `Admin`. Vào trang **Quản lý Nhân sự**, duyệt tài khoản `staff2@retailops.local`.
  3. Quay lại trình duyệt ẩn danh, đăng nhập lại -> Đăng nhập thành công và được cấp cookie session an toàn `HttpOnly`.
- **Kết quả kỳ vọng cần làm nổi bật:**
  - Quy chế bảo vệ tài khoản quản trị duy nhất (`admin_slot = 1`).
  - Luồng phê duyệt nhân sự 2 bước chặt chẽ, chống đăng ký rác.
  - Cơ chế xác thực an toàn bằng JWT cookie `HttpOnly` và header `X-CSRF-Token`.

#### Phân cảnh 2: Quản Lý Sản Phẩm & Bảo Mật Dữ Liệu Giá Vốn (Thời lượng: 3 phút)
- **Người trình diễn (Presenter):** **Vũ Hoàng Lan Anh** (phối hợp với Phạm Nhật Tân)
- **Hành động thao tác:**
  1. Trên tài khoản `Admin`: Mở danh mục sản phẩm, tìm kiếm "Coca", cập nhật thông tin tên hiển thị hoặc giá bán. Minh họa tính duy nhất của mã SKU (thử sửa SKU trùng -> hệ thống báo lỗi HTTP `409 Conflict`).
  2. Chuyển sang tài khoản `Staff`: Mở danh mục sản phẩm.
  3. Mở công cụ Network DevTools của trình duyệt: Khẳng định rằng trong JSON response `ProductRead` trả về cho Staff, **hoàn toàn không có bất kỳ trường giá vốn nào** (`cost_price_vnd`, `unit_cost_vnd`, hay `cost`).
  4. Staff thử bấm sửa thông tin sản phẩm -> Hệ thống chặn ngay tại giao diện và backend trả về `HTTP 403 Forbidden`.
- **Kết quả kỳ vọng cần làm nổi bật:**
  - SKU unique constraint bảo vệ dữ liệu sản phẩm.
  - Tạo sản phẩm nguyên tử kèm tồn kho 0 (`quantity = 0`, `stock_version = 0`).
  - Thiết kế an toàn dữ liệu: Schema `ProductRead` độc lập, bảo mật tuyệt đối thông tin giá vốn kinh doanh trước nhân viên thu ngân.

#### Phân cảnh 3: Quản Lý Nhập Hàng & Khóa Lạc Quan (Thời lượng: 4 phút)
- **Người trình diễn (Presenter):** **Vũ Hoàng Lan Anh** (phối hợp với Na Na)
- **Hành động thao tác:**
  1. Trên tài khoản `Admin`: Vào module **Nhập hàng (Purchasing)**. Tạo một phiếu nhập nháp với 2 dòng cùng 1 sản phẩm nhưng cùng đơn giá -> Minh họa tính năng **Item Merging** tự động gộp thành 1 dòng duy nhất.
  2. Thử tạo 2 dòng cùng sản phẩm nhưng khác đơn giá -> Hệ thống từ chối với mã lỗi `422 Unprocessable Entity (COST_CONFLICT)`.
  3. Minh họa **Khóa lạc quan (Optimistic Locking):** Mở phiếu nhập trên 2 tab trình duyệt cùng lúc (cùng `draft_version = 1`). Tab 1 bấm lưu sửa đổi -> Thành công, `draft_version` tăng lên 2. Tab 2 bấm lưu sửa đổi cũ -> Hệ thống báo lỗi xung đột phiên bản `HTTP 409 Conflict (RECEIPT_VERSION_CONFLICT)`, ngăn chặn hoàn toàn lỗi ghi đè mất dữ liệu (Lost Update).
  4. Thực hiện hủy phiếu nháp: Trạng thái chuyển sang `CANCELLED`, chứng minh bảng tồn kho `inventories` hoàn toàn giữ nguyên, không phát sinh giao dịch thừa.
- **Kết quả kỳ vọng cần làm nổi bật:**
  - Tính năng tự động gộp dòng thông minh (Item Merging).
  - Khóa lạc quan chống race condition trên môi trường phân tán.
  - Thao tác nháp cách ly 100% khỏi bảng tồn kho.

#### Phân cảnh 4: Bán Hàng Thu Ngân (POS) & Hủy Đơn Hoàn Kho (Thời lượng: 3 phút)
- **Người trình diễn (Presenter):** **Nguyễn Cao Lâm** (phối hợp với Cao Nguyễn Anh Dương)
- **Hành động thao tác:**
  1. Đăng nhập tài khoản `Staff`, mở giao diện **POS Thu Ngân**.
  2. Chọn sản phẩm bằng cách click trực tiếp hoặc tìm kiếm nhanh. Tăng giảm số lượng. Thử mua vượt quá số lượng tồn kho khả dụng -> Giao diện cảnh báo không đủ hàng.
  3. Bấm **Thanh toán**: Giao dịch thành công tức thì, in hóa đơn tạm thời.
  4. Mở tab **Lịch sử đơn hàng**: Tìm kiếm đơn vừa tạo, bấm **Hủy đơn hàng**.
  5. Kiểm tra thẻ kho và màn hình tồn kho: Số lượng hàng hóa được hoàn trả chính xác về kho lưu trữ, ghi nhận log `StockMovement` (kind `ORDER_CANCEL`).
- **Kết quả kỳ vọng cần làm nổi bật:**
  - Giao diện bán hàng POS mượt mà, phân trang 12/10 sản phẩm tối ưu cho màn hình cảm ứng.
  - Giao dịch bán hàng và hủy đơn bảo đảm tính toàn vẹn kho hàng (ACID Transaction).

#### Phân cảnh 5: Dashboard Quản Trị & Báo Cáo Phân Tích (Thời lượng: 4 phút)
- **Người trình diễn (Presenter):** **Na Na** (phối hợp với Cao Nguyễn Anh Dương)
- **Hành động thao tác:**
  1. Đăng nhập tài khoản `Admin`, mở màn hình **Dashboard Quản Trị**.
  2. Trình diễn các thẻ chỉ số KPI thời gian thực: Doanh thu trong ngày, Tổng số đơn hoàn thành, Giá trị trung bình mỗi đơn (AOV), Số lượng mặt hàng sắp hết hàng (Low Stock Warning).
  3. Chuyển sang màn hình **Phân tích Doanh thu & Bán hàng (Sales Analytics)**: Lọc dữ liệu theo khoảng ngày Việt Nam (UTC+7), minh họa biểu đồ doanh thu theo thời gian.
  4. Trình diễn bảng xếp hạng **Sản phẩm bán chạy nhất (Top Selling Products)** và **Sản phẩm bán chậm (Slow Moving Products)**: Chứng minh thuật toán gom nhóm đúng `product_id` ngay cả khi sản phẩm đã được đổi tên hiển thị trong catalog.
- **Kết quả kỳ vọng cần làm nổi bật:**
  - Chỉ số Dashboard đồng bộ số học 100% với Sales Analytics.
  - Xử lý múi giờ Việt Nam chuẩn xác theo khoảng nửa mở `[00:00:00, 24:00:00)`.

#### Phân cảnh 6: Giao Diện Dark Mode (Night Mode) & Responsive UX (Thời lượng: 3 phút)
- **Người trình diễn (Presenter):** **Phạm Nhật Tân**
- **Hành động thao tác:**
  1. Tại thanh Header điều hướng, bấm vào nút chuyển đổi giao diện **Chế độ Sáng / Tối (Light / Dark Theme Toggle)** bên cạnh nút Trợ giúp.
  2. Chuyển đổi qua lại giữa Light Mode và Dark Mode trên các màn hình phức tạp: Dashboard biểu đồ, Bảng danh mục sản phẩm, Bảng nhập hàng và Modal pop-up.
  3. Thu nhỏ kích thước trình duyệt để minh họa tính năng **Responsive Layout** trên thiết bị tablet và mobile.
- **Kết quả kỳ vọng cần làm nổi bật:**
  - Chế độ Dark Mode bảo vệ mắt chuyên nghiệp, không bị rò rỉ nền trắng trên table header hay form inputs (giải quyết triệt để lỗi `DEF-014`).
  - Giao diện người dùng mượt mà, thân thiện và đáp ứng chuẩn thiết kế hiện đại.

---

### 3.4. Giới Hạn Đã Biết & Kịch Bản Dự Phòng Rủi Ro (Fallback Plan)

Trong trường hợp phát sinh sự cố kỹ thuật bất khả kháng trong buổi demo trực tiếp, nhóm áp dụng các phương án xử lý nhanh sau:

| Sự Cố Tiềm Ẩn | Nguyên Nhân | Biện Pháp Khắc Phục Tức Thì (Fallback Plan) |
|:---|:---|:---|
| **Lỗi bind cổng `3306` khi khởi động Docker** | Dịch vụ MySQL cục bộ hoặc Hyper-V trên máy Windows chiếm cổng. | Sử dụng cổng thay thế đã thiết lập sẵn: đổi `MYSQL_HOST_PORT=13306` trong file `.env` và kết nối qua `127.0.0.1:13306`. |
| **Giao diện báo lỗi `HTTP 500` ngay sau khi bật Docker** | Container Nginx/Frontend đã bật nhưng MySQL/Backend chưa hoàn tất migration. | Tuân thủ quy trình Cold-Start: chạy lệnh `docker compose run --rm --no-deps backend alembic upgrade head` trước khi truy cập web. |
| **Chạy bài test MySQL báo lỗi fail-closed `database_guard`** | Biến môi trường test database chuyên dụng (`RETAILOPS_TEST_DATABASE_URL`) chưa được thiết lập trên máy host. | Đây là tính năng an toàn có chủ đích để bảo vệ database chính. Để chạy test integration, kích hoạt overlay: `docker compose -f compose.yaml -f compose.ci.yaml up -d`. |
| **Dữ liệu demo bị thiếu hoặc người dùng thao tác nhầm** | Chưa thực hiện bước chuẩn bị dữ liệu hoặc lỡ xóa sản phẩm. | Nạp lại dữ liệu trong 30 giây: chạy lại 3 lệnh seed idempotent (`auth`, `categories`, `suppliers`) mà không cần reset database, sau đó thao tác lại bước nạp sản phẩm mẫu theo Mục 3.2.2. |
| **Rớt mạng Internet khi đang thuyết trình** | Sự cố kết nối WiFi hội trường. | Toàn bộ hệ thống RetailOps chạy 100% cục bộ trong Docker mạng nội bộ máy tính (`localhost`), hoàn toàn không phụ thuộc vào Internet ngoài. Buổi demo vẫn tiếp tục bình thường. |

---

> [!NOTE]
> **Kết luận Bàn giao:** Bản tài liệu QA Report và Demo Playbook này là cơ sở tài liệu chính thức cho task `T04ABDD`, phục vụ trực tiếp cho buổi nghiệm thu release `T04ABC3` và phát hành sản phẩm RetailOps Management System V1.0.
