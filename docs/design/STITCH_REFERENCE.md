# RetailOps V1.0 — Stitch Design Reference

## Google Stitch Project

https://stitch.withgoogle.com/projects/201020714942235892

## Design Direction

**Quiet Utility Green**

- Minimalist, desktop-first và responsive.
- Ưu tiên tính dễ sử dụng và hành động chính.
- Giao diện tiếng Việt.
- Hạn chế trang trí không cần thiết.

## Design Status

**Approved with Conditions — Frontend Implementation Baseline**

Thiết kế đã đủ điều kiện để bắt đầu triển khai React. Các vấn đề responsive còn lại cần được kiểm thử trên ứng dụng thực tế.

## Source of Truth

Thứ tự ưu tiên:

1. `docs/requirement/RetailOps_SRS_Approved.md` — Yêu cầu nghiệp vụ và phân quyền.
2. `docs/design/RetailOps_V1.0_Frontend_Handoff_Design_Freeze.md` — Danh sách màn hình chính thức, node ID, component và UI states.
3. `docs/design/RETAILOPS_UI_DESIGN_BRIEF_V1.md` — Design system và nguyên tắc UX.
4. Google Stitch — Tham khảo trực quan.

## Implementation Rules

- Chỉ sử dụng các màn hình canonical được liệt kê trong Frontend Handoff.
- Không sử dụng các phiên bản POS hoặc AI cũ.
- Không tự thêm chức năng ngoài SRS V1.3.
- Không sao chép nguyên HTML xuất từ Stitch vào React.
- Kiểm tra responsive và accessibility trên ứng dụng thực tế.
- Backend là nơi thực thi phân quyền và bảo vệ dữ liệu.

## Notes

Google Stitch là nguồn tham khảo thiết kế, không phải bằng chứng cho việc các chức năng đã được triển khai hoặc kiểm thử thành công.