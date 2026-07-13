# Các vấn đề nghiệp vụ cần Dược Nam Hà (DNH) xác nhận

*Chuẩn bị cho buổi họp báo cáo tiến độ ngày 16/07/2026. Gửi trước để buổi họp tập trung vào quyết định thay vì giải thích.*

Hệ thống báo cáo/cảnh báo hiện đã chạy trên dữ liệu thật, cập nhật gần thời gian thực từ Bravo. Tuy nhiên có 6 điểm dưới đây hiện đang dùng **giả định tạm thời** vì chưa có xác nhận chính thức từ DNH — số liệu vẫn đúng về mặt kỹ thuật (tính đúng theo công thức đang chọn) nhưng công thức đó có thể chưa khớp quy ước nội bộ của DNH. Càng chốt sớm, số liệu báo cáo/cảnh báo càng đáng tin cậy.

---

## 1. Cách tính "ngày quá hạn" của công nợ

**Đang dùng tạm**: Ngày đến hạn = Ngày hóa đơn (DocDate) + Số ngày công nợ (payment term). Quá hạn = ngày hiện tại vượt qua ngày đến hạn này.

**Cần DNH xác nhận**: Đây có đúng là cách tính chính thức DNH đang áp dụng không? (Có phương án khác thường gặp: tính từ ngày xuất hóa đơn điện tử, hoặc từ ngày ghi nhận công nợ trên hệ thống kế toán, có thể lệch vài ngày so với DocDate).

*Lý do hỏi kỹ: đã từng có bất đồng về cách tính này trong hợp đồng trước đây — cần chốt bằng văn bản để tránh lặp lại.*

## 2. Định nghĩa "Quý" trong chính sách thu nhập QĐ 0429-2 (khối OTC Miền Nam)

**Đang dùng tạm**: Quý dương lịch chuẩn (Q1 = T1-T3, Q2 = T4-T6, Q3 = T7-T9, Q4 = T10-T12).

**Cần DNH xác nhận**: QĐ 0429-2 có dùng đúng quy ước quý dương lịch này để tính "% đạt chỉ tiêu quý" (ảnh hưởng tới cảnh báo mất thưởng quý) không, hay theo 1 mốc khác (vd quý tài chính lệch tháng)?

## 3. Công thức tính tồn kho hiện tại từ Bravo

**Hiện trạng**: Đã thử tính tồn kho hiện tại trực tiếp từ dữ liệu thẻ kho Bravo, đối chiếu với 1 mã hàng cụ thể thì lệch khoảng 19 lần so với số liệu đã biết là đúng — nên **chưa dùng** công thức tự tính này cho báo cáo/cảnh báo tồn kho.

**Cần DNH hỗ trợ**: Công thức/bảng chuẩn để tính đúng số lượng tồn kho hiện tại của 1 mã hàng từ dữ liệu Bravo (thẻ kho, tồn kho đầu kỳ...) — hoặc xác nhận có bảng nào trên Bravo đã có sẵn số tồn tính đúng mà nhóm chưa biết tới.

## 4. Nhóm 9.287 khách hàng có `CustomerType = 2`

**Hiện trạng**: Đã xác nhận và loại 1 mã khách hàng cụ thể (NCC100122) ra khỏi tính toán công nợ vì đây thực chất là nhà cung cấp, không phải khách hàng. Rà lại thấy còn 9.287 bản ghi khác cũng mang `CustomerType = 2` — CHƯA loại các bản ghi này (chỉ loại đúng 1 mã đã xác nhận).

**Cần DNH xác nhận**: `CustomerType = 2` có phải là quy ước chung cho "không phải khách hàng thật" (nhà cung cấp, nội bộ...) không? Nếu đúng, cần loại toàn bộ nhóm này khỏi các báo cáo/cảnh báo công nợ.

## 5. Nguồn dữ liệu KPI cho chức danh TP/PP/TBP

**Hiện trạng**: KPI của Trưởng phòng (TP), Phó phòng (PP), Trưởng bộ phận (TBP) hiện chỉ có trong 1 file Excel DNH gửi đầu dự án (import 1 lần, không tự cập nhật). KPI của TDV/QLV đã có nguồn cập nhật gần thời gian thực từ Bravo.

**Cần DNH xác nhận**: Có nguồn dữ liệu nào trên Bravo/hệ thống nội bộ chứa KPI của các chức danh quản lý này không, để đồng bộ tự động thay vì dùng file tĩnh đã cũ?

## 6. Chu kỳ cập nhật dữ liệu công nợ/tồn kho dạng tổng hợp sẵn

**Hiện trạng**: 2 bảng công nợ theo kỳ (`receivable_detail`) và tồn kho tổng hợp (`inventory`) hiện là dữ liệu Excel DNH gửi 1 lần đầu dự án — không tự làm mới. (Lưu ý: công nợ đã có nguồn thay thế cập nhật real-time từ Bravo — xem mục 1; tồn kho thì chưa, xem mục 3.)

**Cần DNH xác nhận**: Nếu mục 3 (công thức tồn kho) chưa giải quyết được ngay, DNH có thể cung cấp file Excel tồn kho cập nhật theo chu kỳ nào (hàng tuần/hàng tháng) để thay thế bản dữ liệu cũ không?

---

*Chuẩn bị bởi: MCNA — 13/07/2026*
