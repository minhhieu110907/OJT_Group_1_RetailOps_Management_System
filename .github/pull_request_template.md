# Pull Request — RetailOps

## 1. Tóm tắt thay đổi
<!-- Mô tả ngắn gọn thay đổi và lý do. Giữ PR trong một phạm vi có thể review. -->

## 2. Task và yêu cầu liên quan
- **Mã task/backlog (bắt buộc):**
- **Mục SRS hoặc quy tắc nghiệp vụ liên quan:**
- **Thay đổi phạm vi:** Không / Đã được Product Owner phê duyệt (đính kèm liên kết)
- **Tiêu đề PR:** phải chứa mã task, ví dụ `feat(frontend): initialize React foundation [T3C98D1]`

## 3. Loại thay đổi
- [ ] Tính năng mới (Feature)
- [ ] Sửa lỗi (Bug fix)
- [ ] Tái cấu trúc code (Refactor)
- [ ] Tài liệu / công cụ (Documentation / tooling)
- [ ] Database migration
- [ ] Phát hành (`develop` → `main`)

## 4. Kiểm thử và xác minh
- [ ] Các CI checks phù hợp đã chạy và thành công; nếu chưa, giải thích rõ
- [ ] Đã bổ sung/cập nhật và chạy các bài kiểm thử liên quan
- [ ] Không commit mật khẩu thật, secrets hoặc file `.env` local
- [ ] Đã review authentication/authorization và quyền truy cập (nếu liên quan)
- [ ] Đã review transaction, concurrency và idempotency (nếu liên quan)
- [ ] Đã đánh giá tác động database migration và phương án recovery (nếu liên quan)
- [ ] Đã kiểm tra API contract và tương thích frontend/backend (nếu liên quan)

**Lệnh đã chạy và kết quả thực tế:**
<!-- Không đánh dấu PASS hoặc khẳng định thành công khi chưa thực sự chạy. -->

## 5. Rủi ro và phương án khôi phục
- **Mức rủi ro:** Low / Medium / High
- **Giới hạn đã biết / việc cần làm tiếp:**
- **Phương án rollback hoặc giảm thiểu rủi ro:**
<!-- MySQL DDL có thể implicit commit; không mặc định migration sẽ rollback nguyên tử. -->

## 6. Minh chứng
<!-- Link ảnh chụp, kết quả test, GitHub Actions, API response, tài liệu thiết kế... Không để lộ secrets. -->

## 7. Checklist của reviewer
- [ ] Thay đổi phù hợp yêu cầu đã duyệt, không tự mở rộng scope
- [ ] Các rủi ro Security / Data Integrity đã được đánh giá
- [ ] Không còn vấn đề chặn merge
- [ ] Commit và tiêu đề PR sử dụng mã task có thể truy vết

<!-- Riêng PR develop → main: ghi rõ phạm vi release, version/tag dự kiến,
     kết quả kiểm thử end-to-end, độ an toàn migration, khả năng deploy,
     rollback/recovery. -->
