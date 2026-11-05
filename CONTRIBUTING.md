# Hướng dẫn đóng góp cho RetailOps

Tài liệu này thống nhất quy trình cộng tác Git/GitHub của **nhóm sáu thành viên** phát triển RetailOps.

## 1. Quy ước ngôn ngữ

- **Tiếng Việt** là ngôn ngữ mặc định trong README, hướng dẫn sử dụng, mô tả nghiệp vụ, tài liệu bàn giao và nội dung Pull Request để cả nhóm và ban giám khảo dễ theo dõi.
- Giữ **tiếng Anh** cho tên biến/hàm/class, endpoint, đường dẫn, tên nhánh, Git commands, commit message và những thuật ngữ kỹ thuật cần chính xác.
- Khi viết tài liệu tiếng Việt, có thể giữ các thuật ngữ như `transaction`, `migration`, `CI`, `idempotency`; giải thích ngắn gọn khi cần.
- Không dịch tên định danh trong source code hoặc thay đổi nghiệp vụ chỉ để đồng nhất ngôn ngữ tài liệu.

## 2. Quy tắc nhánh

- `main`: baseline ổn định, phục vụ bản demo/release. **Không push trực tiếp.**
- `develop`: nhánh tích hợp và default branch trên GitHub. **Không push trực tiếp.**
- `feature/<task-slug>`, `fix/<task-slug>`, `chore/<task-slug>`: nhánh làm việc ngắn hạn, tạo từ `develop` mới nhất.

Bắt đầu một task mới:

```powershell
git fetch origin
git switch develop
git pull --ff-only origin develop
git switch -c feature/<task-slug>
```

Không tiếp tục phát triển tính năng mới trên nhánh feature đã được merge. Khi đang làm dở một task, tiếp tục trên nhánh feature hiện tại; không tự động pull `develop` vào nhánh feature khi chưa hiểu tác động.

## 3. Quy định commit message — bắt buộc có mã task

**Mọi commit mới do thành viên chủ động tạo** phải tuân thủ Conventional Commits và chứa **mã task thực có thể truy vết**.

Định dạng:

```text
<type>(<scope>): <short imperative description> [<TASK-ID>]
```

Ví dụ:

```text
feat(frontend): initialize React and Axios integration [T3C98D1]
fix(inventory): prevent negative stock under concurrency [<assigned-task-id>]
test(sales): cover repeated cancellation requests [<assigned-task-id>]
ci(frontend): require lint and production build [<assigned-task-id>]
docs(git): document commit message policy [OPS-001]
```

- **Type:** `feat` (tính năng mới), `fix` (sửa lỗi), `refactor` (cải thiện cấu trúc, không đổi hành vi), `test` (kiểm thử), `docs` (tài liệu), `ci` (CI), `chore` (bảo trì), `perf` (hiệu suất).
- **Scope:** phần bị tác động, chẳng hạn `auth`, `product`, `inventory`, `sales`, `purchasing`, `frontend`, `backend`, `db`, `git`.
- **Description:** dùng tiếng Anh, ngắn gọn, mô tả hành động cụ thể; tránh câu chung chung như “update”, “done” hoặc “fix bug”.
- **Task ID:** sử dụng **đúng mã task đã giao**, ví dụ `T3C98D1`. Công việc nội bộ phải có task được nhóm ghi nhận, ví dụ `OPS-001`. Không tự bịa mã Rikkei hoặc dùng mã task không liên quan chỉ để đáp ứng quy định.
- Nếu task chưa có mã, hãy đăng ký/nhận mã theo dõi **trước khi commit**. Áp dụng cả cho tài liệu, refactor và CI.
- Một commit nên tập trung vào một thay đổi logic có liên quan; không trộn nhiều task độc lập.

Ví dụ lệnh:

```powershell
git commit -m "feat(frontend): initialize React and Axios integration [T3C98D1]"
```

**Tiêu đề PR cũng cần chứa mã task.** Nếu dùng Squash and merge, giữ mã task trong tên commit kết quả. Với merge commit GitHub tự sinh kiểu `Merge pull request #...`, mã task nằm trong PR title và các commit gốc; không bắt buộc sửa subject tự sinh. Các commit lịch sử trước khi ban hành quy định được giữ nguyên.

**Thực thi:** Reviewer cần yêu cầu sửa nếu commit mới không có mã task hợp lệ. Hiện đây là quy ước của nhóm; **chưa có commitlint tự động bắt buộc**.

## 4. Quy trình Pull Request

1. Xác định task, đọc SRS/business rules đã phê duyệt và giới hạn phạm vi thay đổi.
2. Chạy các kiểm thử liên quan; nếu chưa chạy được, ghi rõ nguyên nhân và phần chưa kiểm chứng.
3. Push nhánh đang làm việc và tạo PR hướng vào `develop`.
4. Điền [mẫu Pull Request](.github/pull_request_template.md), đợi CI và code review đạt yêu cầu rồi mới merge.
5. Tech Lead điều phối việc merge. Có thể dùng merge commit nếu muốn giữ các commit task có ý nghĩa, hoặc squash khi phù hợp; tuân thủ quy tắc mã task.
6. Sau khi merge, xóa nhánh remote ngắn hạn nếu không còn sử dụng.

**CI xanh là điều kiện tối thiểu, không chứng minh code không có lỗi.** Khi review cần xem xét authentication/authorization, SQL safety, transaction boundary, concurrency, idempotency, database migrations và dữ liệu đầu vào không tin cậy của AI tools tùy theo phạm vi PR.

**Tuyệt đối không commit** `.env`, secrets, production credentials, dữ liệu khách hàng thật hoặc database local được sinh ra.

## 5. Phát hành từ develop lên main

Chỉ tạo PR `develop` → `main` khi **toàn bộ commit đích** đủ ổn định cho bản phát hành; không bắt buộc merge `main` sau mỗi Sprint.

Trước release cần xác nhận phạm vi và yêu cầu đã phê duyệt, CI, kiểm thử end-to-end, bảo mật và tính toàn vẹn dữ liệu, an toàn migration, khả năng deploy và kế hoạch rollback/khôi phục. Chỉ gắn version tag lên `main` sau khi merge và kiểm chứng.

Không merge toàn bộ `develop` chỉ vì một tính năng đã hoạt động nếu các thay đổi khác trên `develop` còn chưa ổn định.

## 6. Giới hạn thực thi trên GitHub

Khi gói GitHub cho phép, cấu hình rulesets bảo vệ `main` và `develop`: bắt buộc PR, review từ ít nhất một thành viên khác và các status checks phù hợp như `Backend / Ruff + unit`, `Backend / MySQL integration` và `Frontend / Lint + Build` khi frontend đã tồn tại.

Cho đến khi xác minh rulesets thực sự được enforce, các quy tắc trên vẫn là **quy ước nhóm**, chưa phải rào chắn kỹ thuật. Người quản lý repository cần giám sát direct push. Nếu sử dụng path filtering, cần kiểm tra required checks để tránh trạng thái Pending khi workflow bị bỏ qua; không xem `Skipped` là bằng chứng frontend đã được kiểm thử.
