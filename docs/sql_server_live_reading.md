# Đọc toàn bộ dữ liệu SQL Server theo kiến trúc hybrid

Cập nhật ngày 14/08/2026 trên database chính `NH_Report_TM`.

## Độ phủ đã đo thực tế

Service account nhìn thấy và có quyền đọc/thực thi trên toàn bộ 140 object nghiệp vụ hiện có:

- 99 bảng.
- 25 view.
- 16 stored procedure.
- 1.941 cột trước khi áp chính sách bảo mật ứng dụng.
- Không có object nào trong catalog bị thiếu quyền `SELECT`/`EXECUTE` tương ứng.

Chatbot đưa 139 object và 1.934 cột vào catalog tìm kiếm. Bảng `dbo.DIM_Pass` bị loại cố định vì chứa thông tin đăng nhập; “đọc hết dữ liệu nghiệp vụ” không đồng nghĩa phát tán credential.

30/41 view/procedure/function có thể đọc definition. Còn 11 module không trả definition và quyền đọc `sys.sql_expression_dependencies` chưa được cấp. Hai gap này không ngăn việc đọc bảng/view, nhưng phải được nêu rõ khi phân tích logic module chưa đủ bằng chứng.

## Dataflow runtime

1. Câu hỏi thuộc báo cáo chuẩn đã đối chiếu tiếp tục dùng template trên `warehouse.db`.
2. Với câu hỏi ad-hoc, hệ thống tìm object/cột liên quan trong catalog SQL Server theo từ khóa nghiệp vụ.
3. Nếu warehouse chưa có bảng/cột, C-Level/Admin được phép chạy T-SQL read-only trực tiếp trên SQL Server chính.
4. Kết quả bị giới hạn 200 dòng ở tầng thực thi và tối đa 20 dòng gửi vào model; truy vấn có timeout và được audit.
5. Nếu schema local báo `no such table/column`, catalog SQL Server liên quan được đính kèm tự động để model chuyển sang nguồn live thay vì kết luận sai rằng không truy cập được dữ liệu.

Catalog được cache một giờ trong RAM. Nếu có snapshot `data/sql_catalog/latest.json`, hệ thống đọc snapshot để phản hồi nhanh; nếu chưa có snapshot, hệ thống tự đọc metadata live một lần rồi cache.

## Lớp an toàn

- Chỉ cho phép một câu `SELECT` hoặc `WITH ... SELECT`.
- Chặn ghi/sửa/xóa, `SELECT INTO`, `EXEC`, `WAITFOR`, `DBCC`, truy cập file/network và truy vấn chéo database.
- Chặn `SELECT *`; bắt buộc chỉ định cột.
- Chặn cứng `dbo.DIM_Pass` kể cả khi service account có quyền đọc.
- Truy vấn SQL Server live chỉ mở cho C-Level/Admin không bị scope. Tài khoản theo vùng/kênh không được dùng raw SQL vì chưa thể chứng minh row-level filter đúng cho mọi bảng; các tài khoản này vẫn dùng báo cáo chuẩn đã ép scope ở tầng code.
- Stored procedure được tìm và đọc definition, nhưng chatbot không được `EXEC` tùy ý vì không phải procedure nào cũng được chứng minh chỉ đọc.

## Vận hành catalog

Chạy từ thư mục gốc repo:

```powershell
python scripts/build_sql_catalog.py
```

Policy mặc định nằm tại `config/sql_catalog_policy.json`. Dược Nam Hà có thể bổ sung object cấm hoặc phân loại cột nhạy cảm mà không phải sửa logic truy vấn.
