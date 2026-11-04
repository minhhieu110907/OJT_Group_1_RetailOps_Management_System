# ĐẶC TẢ YÊU CẦU PHẦN MỀM

Phạm vi: hệ thống quản lý bán hàng, nhập hàng, tồn kho, phân tích kinh doanh và trợ lý AI cho một cửa hàng/một kho. Tài liệu mô tả yêu cầu V1, giữ nguyên danh mục 63 task và phản ánh các quyết định Product Owner đã chốt đến ngày 03/11/2026. Trạng thái: Approval Candidate — chờ Product Owner ký duyệt.

# PHẦN 1 — GIỚI THIỆU VÀ PHẠM VI

## 1.1 Giới thiệu RetailOps

RetailOps là hệ thống nội bộ cho một cửa hàng và một kho, hỗ trợ quản lý sản phẩm, nhà cung cấp, nhập hàng, tồn kho, bán hàng tại quầy, phân tích kinh doanh và trợ lý AI chỉ đọc.

## 1.2 Mục tiêu hệ thống

Hệ thống hướng tới một nguồn dữ liệu nhất quán cho nhập, bán, hủy và kiểm kê; ngăn tồn kho âm, giao dịch lặp và truy cập sai quyền. Các báo cáo và câu trả lời AI phải dựa trên dữ liệu đã commit từ business services.

## 1.3 Phạm vi và giới hạn V1

V1 có hai vai trò ADMIN và STAFF, một cửa hàng, một kho, POS trực tiếp và tiền VND. Không có nhiều chi nhánh/kho, bán hàng online, thanh toán thật, trả hàng/hoàn tiền, thuế/khuyến mãi, đa tiền tệ, kế toán đầy đủ hoặc AI thực hiện thao tác ghi. INV-05, ANA-05 và ENG-10 là P1, chỉ triển khai sau khi P0 đạt quality gate.

# PHẦN 2 — MÔ TẢ TỔNG QUAN HỆ THỐNG

## 2.1 Actors và quyền chính

| Actor | Vai trò và quyền chính |

| --- | --- |

| Admin | Quản lý tài khoản Staff, master data, purchasing, kiểm kê; được POS; xem và hủy mọi đơn COMPLETED trong cùng ngày; dùng Dashboard, Analytics và AI. |

| Staff | Đăng nhập sau khi được duyệt; xem sản phẩm, tồn kho, movement đã lọc và mọi đơn; được POS; chỉ hủy đơn mình tạo trong tối đa 15 phút và cùng ngày Việt Nam. |


## 2.2 Nhóm chức năng chính

Các nhóm chính gồm xác thực và phân quyền; sản phẩm/danh mục; nhà cung cấp/nhập hàng; tồn kho; POS/đơn hàng; phân tích kinh doanh; AI read-only; hạ tầng bất đồng bộ; kỹ thuật, frontend, kiểm thử và bàn giao.

## 2.3 Quy trình nghiệp vụ tổng quan

Staff đăng ký và chờ Admin duyệt trước khi đăng nhập. Admin quản lý master data và xác nhận phiếu nhập để tăng tồn; Admin/Staff checkout để tạo đơn COMPLETED và trừ tồn; hủy hợp lệ hoàn tồn đúng một lần. Dashboard và AI chỉ đọc dữ liệu đã commit; email được gửi bất đồng bộ qua Transactional Outbox sau commit.

## 2.4 Nguyên tắc phân quyền

Backend kiểm tra trạng thái ACTIVE, role, resource scope, ownership và field-level scope ở mọi API nội bộ. Pending/Rejected không truy cập nghiệp vụ; Staff không thấy giá nhập, giá vốn hoặc lý do điều chỉnh nội bộ. UI chỉ phản ánh quyền đã được backend thực thi, không phải lớp bảo vệ duy nhất.

# PHẦN 3 — YÊU CẦU CHỨC NĂNG VÀ DANH MỤC CÔNG VIỆC

Phần này giữ nguyên 63 mã task và thứ tự 13 nhóm từ danh mục công việc nguồn. Các task hạ tầng, kỹ thuật, frontend, QA và bàn giao được mô tả đúng bản chất công việc triển khai.

## 3.1 Xác thực và phân quyền

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| AUTH-01 | Đăng ký tài khoản Staff | Người dùng công khai đăng ký tài khoản Staff bằng email và mật khẩu; hệ thống tạo tài khoản PENDING_APPROVAL và không cấp quyền nội bộ. Người bị REJECTED chỉ được gửi lại yêu cầu sau khi xác minh quyền kiểm soát tài khoản, tối đa một lần trong 24 giờ, giữ nguyên User ID và lịch sử; cơ chế xác minh cụ thể phải được khóa trong Technical Design. Email chuẩn hóa chỉ thuộc một User, và yêu cầu lặp khi đang PENDING không tạo User, approval request hoặc notification mới. |

| AUTH-02 | Đăng nhập, đăng xuất và quản lý phiên | Hệ thống có một tài khoản Admin được seed có kiểm soát; không có đăng ký Admin công khai. Staff đăng nhập bằng email và mật khẩu; access JWT có thời hạn 15 phút, phiên tuyệt đối tối đa 8 giờ, refresh token rotation, access token trong memory và refresh token trong cookie HttpOnly, Secure với biện pháp bảo vệ CSRF/Origin phù hợp. Đăng xuất phải revoke session phía server để chặn cả access token còn hạn; Staff đặt lại mật khẩu bằng token email một lần, còn phục hồi Admin là thao tác vận hành thủ công trên đúng Admin hiện có. |

| AUTH-03 | Duyệt và từ chối đăng ký Staff | Admin duyệt hoặc từ chối hồ sơ Staff đang chờ; hệ thống lưu lịch sử và chỉ cho transition hợp lệ đầu tiên thành công khi có xử lý đồng thời. Cùng transaction đổi trạng thái, hệ thống ghi Outbox Event bền vững; publisher chỉ đưa event ra hàng đợi và gửi email sau khi transaction đã commit. V1 không triển khai khóa hoặc mở khóa Staff. |

| AUTH-04 | Phân quyền truy cập theo vai trò | Hệ thống chỉ cho tài khoản ACTIVE truy cập API nội bộ và kiểm tra vai trò, ownership, phạm vi tài nguyên cùng các trường dữ liệu ở backend. Admin có toàn quyền nghiệp vụ đã được cấp; Staff được POS, xem sản phẩm, tồn kho và mọi đơn nhưng chỉ hủy đơn mình tạo đúng điều kiện. Dashboard, Analytics và AI chỉ dành cho Admin. |

| AUTH-05 | Thông báo đăng ký mới cho Admin | Khi đăng ký Staff hợp lệ được tạo, hệ thống đồng thời tạo đúng một thông báo in-app cho Admin trong cùng transaction. Retry hoặc yêu cầu đăng ký lặp không được tạo thông báo trùng; Admin có thể dùng thông báo để mở danh sách hồ sơ đang chờ. |


## 3.2 Sản phẩm và danh mục

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| PROD-01 | Quản lý sản phẩm | Admin tạo, cập nhật, ngừng sử dụng hoặc kích hoạt lại sản phẩm; hệ thống kiểm tra SKU, giá bán nguyên VND lớn hơn 0 và các dữ liệu bắt buộc. Sản phẩm mới luôn có tồn kho 0 và không được sửa tồn qua màn hình sản phẩm; Product INACTIVE bị chặn khỏi POS và nhập mới nhưng vẫn giữ lịch sử, tồn hiện có và cho phép Admin điều chỉnh kho có audit. |

| PROD-02 | Quản lý danh mục | Admin tạo, sửa và chuyển trạng thái ACTIVE/INACTIVE cho danh mục. Danh mục INACTIVE không được gán cho sản phẩm mới nhưng không tự làm inactive các sản phẩm đang tham chiếu và không xóa cascade dữ liệu lịch sử. |

| PROD-03 | Tìm kiếm, lọc và phân trang sản phẩm | Admin và Staff tra cứu danh sách sản phẩm bằng tìm kiếm, lọc trạng thái/danh mục, sắp xếp và phân trang. Hệ thống trả kết quả theo thứ tự ổn định, giới hạn kích thước trang và chỉ nhận các trường sắp xếp được cho phép. |

| PROD-04 | Xem chi tiết sản phẩm | Admin và Staff xem chi tiết sản phẩm gồm SKU, giá bán, trạng thái, danh mục và tồn kho hiện tại theo quyền. Backend không trả giá nhập, giá vốn hoặc trường quản trị nhạy cảm cho Staff; sản phẩm inactive vẫn hiển thị khi cần đối chiếu lịch sử. |


## 3.3 Nhà cung cấp và nhập hàng

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| PUR-01 | Quản lý nhà cung cấp | Admin tạo, sửa, ngừng sử dụng, kích hoạt lại và tra cứu nhà cung cấp. Supplier INACTIVE không được chọn cho phiếu nhập mới hoặc xác nhận mới, nhưng mọi phiếu nhập lịch sử vẫn giữ nguyên liên kết và snapshot cần thiết. |

| PUR-02 | Tạo và sửa phiếu nhập nháp | Admin tạo và chỉnh sửa phiếu nhập DRAFT, gồm nhà cung cấp, sản phẩm, số lượng nguyên dương và đơn giá nhập nguyên VND không âm. Trong cùng phiếu DRAFT, backend chuẩn hóa và gộp các dòng cùng Product, cùng Unit Cost bằng cách cộng Quantity; cùng Product nhưng khác Unit Cost bị từ chối bằng lỗi validation. Muốn ghi nhận nhiều mức giá cho một Product, Admin phải tạo các phiếu nhập riêng; hệ thống không tự tính đơn giá trung bình và backend tính tổng chính xác bằng số nguyên VND. Mỗi lần sửa dùng draft_version; phiên bản cũ trả 409 và DRAFT chưa làm thay đổi tồn kho. |

| PUR-03 | Xác nhận phiếu nhập | Admin xác nhận phiếu DRAFT bằng expected_version mới nhất và idempotency key. Hệ thống kiểm tra nhà cung cấp, sản phẩm còn ACTIVE rồi cập nhật phiếu, tăng tồn và ghi Stock Movement trong một transaction; retry không được cộng kho lần hai. Phiếu CONFIRMED trở thành bất biến. |

| PUR-04 | Hủy phiếu nhập nháp | Admin hủy phiếu nhập khi phiếu còn DRAFT và expected_version khớp. Hệ thống chuyển trạng thái đúng một lần, không thay đổi tồn kho; yêu cầu stale hoặc phiếu đã CONFIRMED/CANCELLED bị từ chối. |

| PUR-05 | Lịch sử và chi tiết phiếu nhập | Admin xem danh sách và chi tiết phiếu nhập theo trạng thái, nhà cung cấp, khoảng ngày và phân trang. Lịch sử phải giữ ID tham chiếu, số lượng, Unit Cost, tổng tiền và trạng thái đã chốt; tập trường snapshot tên sản phẩm hoặc nhà cung cấp chưa được phê duyệt đầy đủ và phải xác định trong Data Design trước khi khóa schema. |


## 3.4 Tồn kho

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| INV-01 | Tổng quan tồn kho | Admin và Staff xem tồn kho hiện tại theo sản phẩm, danh mục, trạng thái và tình trạng còn hàng. Hệ thống trả số lượng cùng phiên bản tồn để hỗ trợ đối chiếu; dữ liệu đọc không phải là cam kết giữ hàng cho giỏ POS. |

| INV-02 | Điều chỉnh tồn kho theo kiểm kê thực tế | Admin nhập số lượng kiểm kê thực tế, lý do và expected_stock_version; backend tự tính chênh lệch và cập nhật kho bằng transaction có audit. Nếu version đã cũ, hệ thống trả 409 để kiểm kê lại. Khi số đếm bằng tồn hiện tại, hệ thống chỉ ghi audit, không tạo Stock Movement và không tăng stock_version. |

| INV-03 | Lịch sử biến động kho | Admin xem đầy đủ lịch sử biến động kho; Staff được xem SKU, loại biến động, số lượng, thời điểm và mã tham chiếu. Backend phải loại bỏ giá nhập, giá vốn, lý do nội bộ và dữ liệu cá nhân không cần thiết khỏi phản hồi cho Staff; lịch sử là append-only. |

| INV-04 | Cảnh báo tồn kho thấp | Admin và Staff xem cảnh báo cho sản phẩm ACTIVE có tồn kho bằng 0 hoặc không vượt quá ngưỡng thấp. Ngưỡng P0 mặc định là 5 và phải dùng cùng một định nghĩa ở Inventory, Dashboard và AI. |

| INV-05 | Ngưỡng tồn kho thấp tùy chỉnh | Trong phạm vi P1, Admin cấu hình ngưỡng tồn kho thấp riêng cho từng sản phẩm. Hệ thống dùng ngưỡng riêng thay cho mức mặc định khi tính cảnh báo; thay đổi ngưỡng không làm đổi số lượng tồn hoặc stock_version. Chức năng chỉ triển khai sau khi P0 đạt quality gate. |


## 3.5 Bán hàng và POS

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| SALE-01 | Giỏ hàng POS | Admin và Staff tạo giỏ POS, thêm, đổi số lượng hoặc xóa sản phẩm; hệ thống gộp các dòng trùng sản phẩm và chỉ chấp nhận số lượng nguyên dương. Thêm vào giỏ không giữ tồn kho, sản phẩm INACTIVE không được bán và tổng hiển thị chỉ là báo giá trước checkout. |

| SALE-02 | Thanh toán bán hàng trực tiếp | Admin hoặc Staff checkout với idempotency key và thông tin giá đã xem; backend kiểm tra lại giá và tồn rồi tạo ngay đơn COMPLETED, trừ kho và ghi Stock Movement trong một transaction. Nếu giá thay đổi, hệ thống từ chối toàn bộ với 409 PRICE_CHANGED, trả giá mới để người bán xác nhận và thử lại bằng ý định mới; lần từ chối không tạo đơn hoặc biến động kho. |

| SALE-03 | Lịch sử và chi tiết đơn hàng | Admin và Staff xem danh sách mọi đơn và chi tiết đơn theo tìm kiếm, bộ lọc ngày, trạng thái và phân trang. Lịch sử phải giữ ID tham chiếu, số lượng, giá bán, tổng tiền, người tạo và trạng thái; tập trường snapshot mô tả sản phẩm phải được xác định trong Data Design. Quyền đọc không cho Staff sửa hoặc hủy đơn của người khác. |

| SALE-04 | Hủy đơn hàng có điều kiện | Staff chỉ được hủy đơn COMPLETED do mình tạo khi thời gian đã qua không quá 15 phút và vẫn trong cùng ngày kinh doanh Việt Nam. Admin được hủy mọi đơn COMPLETED trong cùng ngày mà không bị giới hạn ownership hoặc 15 phút. Khi thành công, hệ thống bắt buộc lưu lý do, actor và thời điểm, chuyển trạng thái và hoàn tồn đúng một lần trong một transaction. |

| SALE-05 | Idempotency cho checkout | Checkout bắt buộc dùng idempotency key có phạm vi User ID, operation và key, được lưu 24 giờ sau khi hoàn tất. Cùng key và cùng payload phải phát lại kết quả cũ; payload khác trả 409, còn yêu cầu đồng thời chờ ngắn rồi trả kết quả hoặc lỗi 409/425 mà không tạo đơn hay trừ kho lặp. |


## 3.6 Phân tích kinh doanh

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| ANA-01 | Tổng hợp doanh thu và chỉ số bán hàng | Admin xem doanh thu, số đơn COMPLETED, số đơn CANCELLED và AOV theo kỳ; mặc định là ngày kinh doanh hiện tại tại Việt Nam. Doanh thu và AOV chỉ tính các đơn còn trạng thái COMPLETED, loại toàn bộ đơn CANCELLED; số đơn CANCELLED được thống kê theo ngày hoặc kỳ bán ban đầu của đơn, không theo thời điểm hủy. Tiền dùng số nguyên VND và AOV được làm tròn ROUND_HALF_UP đến VND gần nhất. |

| ANA-02 | Sản phẩm bán chạy | Admin xem xếp hạng sản phẩm bán chạy theo tổng số đơn vị đã bán trong kỳ, mặc định 7 ngày. Hệ thống chỉ cộng item của các đơn còn trạng thái COMPLETED và loại item thuộc đơn CANCELLED, kể cả đơn đã từng hoàn tất trước khi bị hủy. Kết quả được sắp xếp ổn định và có thể trả doanh thu phụ trợ. |

| ANA-03 | Sản phẩm bán chậm | Admin xem sản phẩm bán chậm khi Product ACTIVE, tồn kho lớn hơn 0, first_stocked_at cách hiện tại hơn 7 ngày và lượng bán không quá 2 đơn vị trong 30 ngày gần nhất. first_stocked_at là thời điểm đầu tiên tồn kho chuyển từ 0 sang số dương qua nhập hàng hoặc điều chỉnh hợp lệ; không dùng product.created_at. Kết quả gồm cả sản phẩm không bán trong kỳ và không áp Product Age ≥30 ngày. |


| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| ANA-04 | Phân tích tồn kho thấp | Admin xem phân tích tồn kho thấp cho sản phẩm ACTIVE có tồn không vượt quá ngưỡng hiệu lực; P0 dùng mức 5 và P1 có thể dùng ngưỡng riêng. Kết quả phải khớp cảnh báo Inventory và nêu rõ kỳ hoặc ngưỡng đã áp dụng. |

| ANA-05 | Xuất báo cáo CSV | Trong phạm vi P1, Admin xuất các báo cáo được cho phép ra CSV theo đúng bộ lọc và quyền hiện tại. Hệ thống giới hạn số dòng, mã hóa an toàn và ngăn công thức nguy hiểm khi mở bằng bảng tính. Chức năng chỉ triển khai sau khi P0 đạt quality gate. |


## 3.7 Trợ lý AI

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| AI-01 | Phân tích kinh doanh bằng ngôn ngữ tự nhiên | Admin đặt câu hỏi kinh doanh bằng ngôn ngữ tự nhiên; trợ lý AI chỉ dùng dữ liệu bán hàng, analytics và tồn kho lấy qua các công cụ được cho phép. Câu trả lời phải nêu dữ liệu hoặc kỳ dùng để suy luận, không tự bịa số liệu và không thực hiện thao tác ghi. |

| AI-02 | Tool calling chỉ đọc cho dữ liệu bán hàng và tồn kho | Hệ thống cung cấp allowlist công cụ chỉ đọc cho AI, xác thực Admin ở mỗi lần gọi và kiểm tra schema tham số trước khi truy vấn business service. AI không được nhận SQL tự do, gọi endpoint ghi hoặc mở rộng phạm vi dữ liệu ngoài quyền của người dùng. |

| AI-03 | Gợi ý nhập hàng có dẫn chứng | Admin yêu cầu gợi ý nhập hàng; hệ thống tổng hợp tồn hiện tại, cảnh báo thấp và tốc độ bán để đưa ra khuyến nghị có dẫn chứng. Kết quả chỉ là đề xuất, không tự tạo supplier, phiếu nhập hoặc thay đổi tồn kho. |

| AI-04 | Xử lý lỗi và độ tin cậy của AI | Hệ thống áp dụng timeout, quota và giới hạn số lần gọi tool cho mỗi yêu cầu AI; lỗi model hoặc tool được trả bằng thông báo an toàn, không lộ dữ liệu kỹ thuật nhạy cảm. Khi không đủ bằng chứng, trợ lý phải nói rõ giới hạn thay vì tạo câu trả lời chắc chắn giả. |


## 3.8 Hạ tầng và xử lý bất đồng bộ

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| INF-01 | Cấu hình Nginx reverse proxy | Nhóm kỹ thuật cấu hình Nginx làm điểm vào cho frontend và backend, định tuyến đúng dịch vụ và chuyển tiếp header theo allowlist. Chỉ chuỗi proxy Nginx/Cloudflare đã cấu hình được tin cậy; client không được tự quyết định địa chỉ IP nguồn qua header giả mạo. |

| INF-02 | Rate limiting bằng Redis | Nhóm kỹ thuật dùng Redis để rate limit theo các khóa độc lập IP và account/email: Login 5/phút/IP và 20/giờ/account; Registration 3/giờ/IP; Forgot Password 3/giờ/IP và email; Refresh 10/phút/session; AI 10/phút/user; Business API 120/phút/user. Khi Redis lỗi, Auth công khai và AI fail-closed, còn POS/nghiệp vụ nội bộ tiếp tục nếu MySQL-backed session/RBAC vẫn an toàn. Chỉ chuỗi proxy Nginx/Cloudflare đã cấu hình được tin cậy; Redis không là nguồn dữ liệu nghiệp vụ có thẩm quyền. |

| INF-03 | RabbitMQ, Celery và worker | MySQL Transactional Outbox lưu business event trong cùng transaction nghiệp vụ. Một Outbox Publisher độc lập polling MySQL và chỉ publish message sau commit; RabbitMQ làm message broker, còn Celery Worker xử lý email bất đồng bộ theo cơ chế at-least-once, idempotent và retry hữu hạn. Không gọi Outbox Publisher là Celery Publisher và không cam kết email external exactly-once; giao dịch đơn hàng, phiếu nhập và tồn kho vẫn commit đồng bộ trong MySQL. |

| INF-04 | Gửi email nghiệp vụ | Hệ thống gửi email nghiệp vụ cho đăng ký, duyệt/từ chối và đặt lại mật khẩu từ các event bền vững. Email không quyết định thành công của giao dịch chính; mỗi nội dung phải tránh lộ trạng thái tài khoản không cần thiết và không chứa token trong log. |

| INF-05 | Xử lý lỗi hàng đợi và phục hồi | Nhóm kỹ thuật dùng Transactional Outbox cho email event: intent được ghi trong cùng transaction nghiệp vụ, còn publisher polling MySQL chỉ publish sau commit. RabbitMQ/Celery worker xử lý at-least-once, idempotent và có retry/replay; broker hoặc worker lỗi không được làm mất intent. Outbox không bảo đảm email bên ngoài exactly-once và không được đặt việc gửi email vào transaction nghiệp vụ. |


## 3.9 Kỹ thuật, kiểm thử và triển khai

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| ENG-01 | Concurrency cho bán hàng | Backend phải kiểm soát các checkout và hủy đơn đồng thời để tồn kho không âm, không oversell và không hoàn kho lặp. Order, Stock, Stock Movement và audit chỉ được commit cùng nhau; lỗi bất kỳ phải rollback toàn bộ. |

| ENG-02 | Nhất quán dữ liệu nhập hàng và tồn kho | Backend dùng một Inventory Service thống nhất cho xác nhận phiếu nhập, bán hàng, hủy đơn và điều chỉnh kho. Mọi thay đổi số lượng phải tạo Stock Movement phù hợp và tăng stock_version trong cùng transaction, trừ no-op kiểm kê đã được quy định. |

| ENG-03 | Khung idempotency dùng chung | Nhóm kỹ thuật xây khung idempotency dùng chung bắt buộc cho checkout, confirm receipt, cancel order và inventory adjustment. Bản ghi có phạm vi User ID, operation và key, kiểm tra fingerprint payload, xử lý request đồng thời và lưu kết quả hoàn tất 24 giờ. |

| ENG-04 | Bảo mật backend | Backend phải hash mật khẩu an toàn, bảo vệ cookie, kiểm tra CSRF/CORS, session, trạng thái tài khoản, RBAC và field-level scope ở server. Hệ thống áp dụng rate limit, validation, secret management và log không chứa mật khẩu, token hoặc dữ liệu nhạy cảm. |

| ENG-05 | Bộ thực thi tool cho AI | Nhóm kỹ thuật xây bộ thực thi tool AI với schema rõ ràng, allowlist, timeout, quota, audit và kiểm tra quyền ở từng lần gọi. Executor chỉ gọi business service đọc dữ liệu, giới hạn kích thước kết quả và không cho model truyền SQL hoặc lựa chọn identity khác. |

| ENG-06 | Kiểm thử tự động | Nhóm kỹ thuật thiết lập unit, integration, security và concurrency tests cho các luồng P0 và bất biến quan trọng; backend business code đặt mục tiêu coverage tối thiểu 80%. Các test khóa, transaction và race condition phải chạy với MySQL phù hợp, không dùng SQLite làm bằng chứng tương đương. |

| ENG-07 | Docker Compose môi trường dự án | Nhóm kỹ thuật đóng gói frontend, backend, MySQL, Redis, RabbitMQ, worker và Nginx bằng Docker Compose. Môi trường phải khởi tạo lại được từ cấu hình mẫu, migration và seed; secrets thật không được commit vào repository. |

| ENG-08 | CI với GitHub Actions | GitHub Actions phải chạy lint, automated tests, migration checks và các kiểm tra bảo mật phù hợp cho pull request vào develop. PR không được merge khi gate thất bại; bản demo hoặc release bị chặn nếu còn lỗi Critical/High hoặc luồng P0 trọng yếu chưa được kiểm thử. |

| ENG-09 | Triển khai bản demo | Nhóm kỹ thuật chuẩn bị một phương án triển khai demo có Nginx, HTTPS, secrets và health check an toàn, kèm runbook tái lập. Cách công khai bản demo có thể là mạng cục bộ, tunnel hoặc hosting tùy môi trường đã xác minh; Cloudflare Tunnel là phương án tham khảo, không phải yêu cầu bắt buộc của V1. |

| ENG-10 | Tối ưu truy vấn | Trong phạm vi P1, nhóm kỹ thuật đo và tối ưu truy vấn chậm hoặc N+1 bằng workload, EXPLAIN và chỉ số trước/sau. Không tối ưu theo cảm giác hoặc làm thay đổi kết quả nghiệp vụ; công việc chỉ bắt đầu sau khi P0 đạt quality gate. |


## 3.10 Tài liệu nghiệp vụ và thiết kế

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| GOV-01 | Khóa phạm vi và mapping quyết định | Product Owner và nhóm dự án khóa phạm vi V1, ghi nhận 14 quyết định đã duyệt và duy trì mapping DEC–task–test. Mọi thay đổi nghiệp vụ sau đó phải qua phê duyệt có kiểm soát; chi tiết kỹ thuật chưa chốt không được ghi thành quyết định của PO. |

| GOV-02 | ERD, migration và seed nền tảng | Nhóm kỹ thuật hoàn thiện ERD, migration và seed cho toàn bộ miền nghiệp vụ V1. Schema phải bảo vệ unique, khóa ngoại, version và các bất biến đã chốt; migration phải chạy lại được trên môi trường sạch. |

| GOV-03 | API contract và danh mục lỗi | Nhóm kỹ thuật chuẩn hóa OpenAPI, request/response và danh mục lỗi cho các phân hệ. Contract phải thể hiện rõ 401/403/409/422/429/503, expected version, PRICE_CHANGED, idempotency, timezone và định dạng số tiền để frontend xử lý nhất quán. |

| GOV-04 | Figma và luồng giao diện cơ sở | Nhóm thiết kế xây Figma cho đăng ký/duyệt, catalog, purchasing, inventory, POS, hủy đơn, dashboard và AI. Luồng phải thể hiện loading, empty, validation, conflict, permission và error states theo contract, không bổ sung chức năng ngoài V1. |


## 3.11 Giao diện người dùng

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| FE-01 | Khung ứng dụng React, routing và auth guard | Frontend tạo khung React/Vite, routing, API client và route guard theo trạng thái phiên và vai trò. Access token chỉ giữ trong memory, refresh dùng cookie HttpOnly; giao diện xử lý nhất quán loading, 401, 403 và phiên hết hạn. |

| FE-02 | Màn hình xác thực và duyệt đăng ký | Frontend cung cấp màn hình đăng ký, đăng nhập, quên/đặt lại mật khẩu, trạng thái chờ và gửi lại yêu cầu sau REJECTED; Admin có màn hình duyệt/từ chối. Giao diện dùng phản hồi công khai chung để hạn chế dò email và hiển thị xung đột khi hồ sơ đã được xử lý ở phiên khác. |

| FE-03 | Giao diện quản lý sản phẩm, danh mục, nhà cung cấp | Frontend cung cấp bảng, form, tìm kiếm, lọc và chuyển trạng thái cho sản phẩm, danh mục và nhà cung cấp theo quyền. Các hành động bị cấm hoặc dữ liệu nhạy cảm không được hiển thị cho Staff; UI vẫn phải dựa vào backend để thực thi quyền. |

| FE-04 | Giao diện phiếu nhập hàng | Frontend cho Admin tạo/sửa phiếu DRAFT, xác nhận, hủy và xem lịch sử phiếu nhập. Giao diện gửi expected_version, hiển thị xung đột 409 và yêu cầu tải lại dữ liệu trước khi người dùng tiếp tục. |

| FE-05 | Giao diện tồn kho và điều chỉnh kho | Frontend hiển thị tổng quan tồn, lịch sử movement và form điều chỉnh kiểm kê cho Admin; Staff chỉ thấy các trường movement được phép. Form adjustment bắt buộc số đếm, lý do và version, đồng thời thông báo rõ trường hợp stale hoặc no-op. |

| FE-06 | Giao diện POS, checkout và lịch sử đơn hàng | Frontend cung cấp giỏ POS, checkout, lịch sử đơn và hủy đơn theo quyền cho Admin/Staff. Khi nhận 409 PRICE_CHANGED, giao diện hiển thị giá mới, yêu cầu xác nhận và retry bằng ý định mới; nút hủy phải phản ánh ownership, thời hạn 15 phút và ngày kinh doanh. |

| FE-07 | Giao diện dashboard, analytics và AI | Frontend cung cấp Dashboard, Analytics và trợ lý AI chỉ cho Admin. Giao diện hiển thị kỳ, timezone, ngưỡng và evidence dùng cho kết quả; lỗi, timeout, quota hoặc dữ liệu không đủ phải được trình bày rõ ràng. |


## 3.12 Kiểm thử và đánh giá

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| QA-01 | Kiểm thử luồng nghiệp vụ đầu cuối | Nhóm QA cùng các thành viên chạy hồi quy các luồng đăng ký–duyệt–đăng nhập, purchasing–inventory, POS–hủy đơn, analytics và AI. Bộ test phải bao phủ quyền, boundary thời gian, stale version, retry/idempotency, Redis/broker outage và các giao dịch đồng thời; chỉ ghi pass khi có bằng chứng thực thi. |

| QA-02 | Đánh giá hiệu năng và rà soát bảo mật | Nhóm QA đo P95 với 10–20 người dùng đồng thời: Product/Category và Inventory Read không quá 300 ms, Checkout và Receipt Confirm không quá 800 ms, Dashboard không quá 1.500 ms; AI có timeout/quota riêng. Đồng thời rà soát auth/RBAC, CSRF, spoofed proxy headers, logs/secrets và ghi rõ máy, dữ liệu cùng workload đo. |


## 3.13 Tài liệu và bàn giao

| Mã task | Tên chức năng/công việc | Đặc tả ngắn gọn |

| --- | --- | --- |

| REL-01 | Tài liệu hướng dẫn chạy và demo | Nhóm dự án hoàn thiện README, hướng dẫn cấu hình, Docker Compose, migration, seed, runbook và kịch bản demo. Tài liệu phải nêu feature map, giới hạn V1, các chức năng P1 và cách phục hồi dịch vụ phụ mà không công bố secrets. |

| REL-02 | UAT, tổng hợp lỗi | Product Owner và nhóm thực hiện UAT, phân loại lỗi và khóa bộ bằng chứng cuối gồm kết quả CI, test, benchmark và demo. Chỉ sẵn sàng bàn giao khi không còn lỗi Critical/High, các luồng P0 quan trọng đã kiểm chứng và mọi hạn chế còn lại được ghi rõ. |


# PHẦN 4 — YÊU CẦU PHI CHỨC NĂNG

| Nhóm yêu cầu | Yêu cầu | Ghi chú kiểm chứng |

| --- | --- | --- |

| Security | Mật khẩu hash an toàn; JWT 15 phút; session tuyệt đối 8 giờ; refresh rotation; revoke server-side; RBAC và field-level scope; CSRF/CORS, validation, secret-safe logs. | Xác minh bằng security tests và review cấu hình. |

| Performance targets | Với 10–20 concurrent users: Product/Category và Inventory Read P95 ≤300 ms; Checkout và Receipt Confirm P95 ≤800 ms; Dashboard P95 ≤1.500 ms. AI có timeout/quota riêng. | Đây là mục tiêu DEC-14, chưa phải benchmark result. |

| Reliability | Transactional Outbox, publisher sau commit, at-least-once worker, retry/replay và quan sát lỗi. Core order/stock/receipt không phụ thuộc broker hoặc email để commit. | Không cam kết email external exactly-once. |

| Data integrity | Không stock âm, oversell, duplicate order, duplicate confirm/restore. Order/Receipt/Stock/Movement/Audit/Idempotency phải nhất quán sau commit hoặc rollback. | Kiểm tra bằng integration và concurrency tests. |

| Retention | Orders, Receipts, Stock Movements và business audit giữ suốt vòng đời dữ liệu demo; idempotency hoàn tất 24 giờ; session/refresh hết hạn dọn sau 30 ngày; password-reset token hết hạn dọn sau 24 giờ; outbox đã xử lý 7 ngày; log ứng dụng 14 ngày. | Outbox chưa xử lý/thất bại không tự xóa; cleanup không làm lộ secrets. |

| Testing & Coverage | Backend business logic coverage mục tiêu ≥80%; bắt buộc test critical flows/invariants, security, concurrency và P0 integration. | Coverage không thay thế kiểm thử hành vi quan trọng. |


| Nhóm yêu cầu | Yêu cầu | Ghi chú kiểm chứng |

| --- | --- | --- |

| CI Quality Gates | PR vào develop phải qua lint, tests, migration checks và security checks phù hợp. Demo/release bị chặn nếu còn Critical/High hoặc critical flow chưa kiểm thử. | Kết quả CI là bằng chứng, không chỉ cấu hình workflow. |

| Deployment constraints | Docker Compose phải tái lập được; Nginx là reverse proxy; secrets không commit; health check không lộ dữ liệu nhạy cảm. Cách public demo được chọn sau khi xác minh môi trường. | Cloudflare Tunnel là tùy chọn, không phải bắt buộc. |


# PHẦN 5 — RÀNG BUỘC, GIẢ ĐỊNH VÀ NGHIỆM THU

## 5.1 Chức năng ngoài phạm vi V1

Ngoài phạm vi V1 gồm Google Login hoặc Social Login; Staff suspension/reactivation; returns/refunds; multi-store hoặc multi-warehouse; Purchase Reversal; e-commerce; thanh toán thật; thuế/khuyến mãi; đa tiền tệ; accounting; forecasting tự động; vector database; multi-agent và các enhancement chưa có change request. Trợ lý AI chỉ đọc dữ liệu qua công cụ được cho phép và không thực hiện thao tác ghi dữ liệu.

## 5.2 Ràng buộc nghiệp vụ trọng yếu

Quantity là số nguyên; tiền là số nguyên VND; Product mới có stock 0. Mọi thay đổi số lượng đi qua Inventory Service và audit. Phiếu CONFIRMED bất biến; sai lệch sau xác nhận xử lý bằng Admin Inventory Adjustment. Hủy đơn tuân thủ ownership, 15 phút và ngày Việt Nam theo role; mọi thao tác nhạy cảm phải idempotent hoặc có version guard như đã chỉ định.

## 5.3 Giả định và giới hạn

Dữ liệu demo là giả lập; đồng hồ server/database được đồng bộ và timestamp lưu UTC, hiển thị theo Asia/Ho_Chi_Minh. Thêm hàng vào giỏ không giữ tồn. Slow-moving dùng stocked age >7 ngày, tồn >0 và bán ≤2 đơn vị trong 30 ngày; kết quả có giới hạn khi sản phẩm từng hết hàng lâu. Các chỉ tiêu P95 và coverage là mục tiêu/chính sách cho đến khi có evidence đo thực tế.

## 5.4 Tiêu chí nghiệm thu tổng thể

Tài liệu phải liệt kê và đặc tả đầy đủ 63 task, nhưng nghiệm thu V1 cốt lõi chỉ bắt buộc hoàn thành phạm vi P0. INV-05, ANA-05 và ENG-10 thuộc P1, không bắt buộc hoàn thành trước demo và chỉ được triển khai sau khi P0 đáp ứng Quality Gates. Nghiệm thu P0 yêu cầu không còn lỗi Critical/High; các invariant transaction, quyền, idempotency, version và outage behavior có test evidence; Docker Compose, migration, seed, runbook, CI, security review và benchmark mục tiêu phải tái lập hoặc kiểm chứng được theo kế hoạch nghiệm thu.

## 5.5 Vấn đề Technical Design còn mở

| Mã | Điểm cần làm rõ |

| --- | --- |

| TD-01 | Cơ chế xác minh quyền kiểm soát tài khoản khi REJECTED reapply. |

| TD-03 | Tập trường snapshot tối thiểu cho Order Item, Receipt Item, Product và Supplier history. |

| TD-04 | Giới hạn field/item, timeout, lock order, retry/backoff và email provider. |

| TD-05 | Benchmark fixture/hardware, timeout AI và phương án public demo phù hợp môi trường. |
