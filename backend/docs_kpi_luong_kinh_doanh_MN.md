# KPI lương kinh doanh vùng MN — trạng thái xác nhận công thức

Nguồn: file `Báo cáo KPI lương kinh doanh_MN.csv` (báo cáo 22/07/2026, ngày chốt V25 25/07/2026),
người dùng cung cấp 23/07/2026.

**QUAN TRỌNG (xác nhận với DA bên DNH, 23/07/2026): bộ KPI này CHƯA áp dụng thực tế cho tháng
7/2026** — vẫn đang ở dạng công thức thử nghiệm/dự thảo, KHÔNG PHẢI số liệu chính thức dùng để trả
lương. Từ đầu năm 2026 đến hết tháng 6/2026, DNH vẫn dùng cách tính KPI CŨ (ngưỡng đạt 80%/50% trên
`fact_tonghopkhachhang`, đã có sẵn trong hệ thống qua `get_employee_kpi`/`get_kpi_ranking`) — 2 hệ
thống KPI hoàn toàn tách biệt, KHÔNG được trộn lẫn khi trả lời người dùng. Chưa rõ khi nào (nếu có)
bộ KPI mới này sẽ chính thức áp dụng — cần hỏi lại DNH khi cần.

**CHƯA có bảng dữ liệu tương ứng trong `warehouse.db`** — không đủ nguồn (`fact_tonghopkhachhang`
hiện chỉ có `amount_ct`/`month_sale_target`/`is_nc`, không có SKU, khách tái đơn, khách active, SP
trọng tâm, ASO...). Vì vậy **chatbot KHÔNG THỂ trả lời các câu hỏi về bộ KPI lương mới này bằng SQL
thật** cho tới khi (1) DNH chính thức áp dụng và (2) có ETL đưa nguồn này vào hệ thống — tài liệu này
chỉ ghi lại công thức đã hiểu để dùng khi triển khai sau, KHÔNG được dùng để AI tự bịa số.

## Cấu trúc 1 dòng báo cáo

Mỗi vùng/QLV/TDV có **nhiều dòng lồng nhau theo cấp bậc** (không phải 1 dòng/người):
- Dòng `Vị trí=TP`: tổng cả vùng (VD "MN" — Trần Thanh Tùng)
- Dòng `Vị trí=QLV`: tổng 1 khu vực do QLV đó phụ trách (gồm cả doanh số các TDV dưới quyền)
- Dòng `Vị trí=TDV` **có mã trùng dòng QLV ở trên nhưng đảo vị trí Mã NV/Mã DMS** (VD dòng QLV
  "Nguyễn Văn Danh" mã `TM23100148`/`ASM03`, ngay dưới có dòng TDV "Nguyễn Văn Danh (QLV)" mã
  `ASM03`/`TM23100148` — đây là bản ghi "bóng" của chính QLV đó trong vai trò 1 TDV, dữ liệu thường
  rỗng/0) — cùng pattern với bản ghi bóng QLV trong `dim_nhanvien` mà hệ thống chatbot đã biết.
- Dòng `Vị trí=CS/TK/PP/CTV`: các vai trò khác (Chợ sỉ, Trưởng khu, Phòng phụ trách, Cộng tác viên).
- Kênh MT (Modern Trade) xuất hiện như 1 dòng `Vị trí=QLV`, Mã NV=`MN1`, Mã DMS=`ASM01` — khớp đúng
  với `dim_nhanvien` hiện có trong hệ thống (xem `schema_context.py`).

## Công thức ĐÃ KIỂM CHỨNG (khớp qua nhiều dòng dữ liệu, có thể tin dùng)

- `%` (cột 8) = `TH / Target` — khớp chính xác ở mọi dòng đã kiểm tra (TP, QLV, TDV).
- `% KH tái đơn` = `SL KH tái đơn / Khoán KH tái đơn` — khớp chính xác (VD 2/3 = 0.6667).
- `Trọng số KPI SP trọng tâm (%)` = `% Hoàn thành × 0.3` — khớp chính xác (0.7665 × 0.3 = 0.22995).
  Gợi ý: 0.3 (30%) có thể là trọng số tối đa dành cho nhóm KPI SP trọng tâm trong tổng cơ cấu lương,
  cần DNH xác nhận đây có phải hằng số cố định hay thay đổi theo vị trí.

## CHƯA XÁC ĐỊNH — cần DNH giải thích trước khi triển khai (KHÔNG được đoán)

- **Trọng số KPI SKU (%)**: thử công thức `TH SKU / Khoán SKU × hệ_số` nhưng hệ số **KHÔNG nhất
  quán** giữa các vị trí — TDV ra ~0.2, QLV và TP ra ~0.5. Trọng số có thể phụ thuộc vị trí
  (TDV/QLV/TP có hệ số khác nhau) hoặc công thức gốc khác hẳn giả thuyết trên.
- **% Thực đạt** và mối quan hệ với `DS SP trọng tâm`/`Khoán SP trọng tâm (%)`: giả thuyết
  `DS SP trọng tâm / (Target × Khoán SP trọng tâm %)` cho kết quả SAI (0.1926 tính ra vs 0.3066
  thực tế) — công thức đúng chưa rõ.
- **Cột DM1/DM2/DM3**: tên viết tắt chưa rõ nghĩa (Danh mục 1/2/3? Doanh mục?), một số dòng có giá
  trị bất thường dạng `453023156700%` (nghi ngờ lỗi định dạng % khi xuất Excel/CSV, giá trị thật có
  thể phải chia lại cho 100 hoặc nhiều hơn — cần xác nhận, KHÔNG dùng trực tiếp).
- **V15/V22/V25** (`TH V15/%V15/Thưởng V15`, tương tự V22, V25): nghi ngờ là 3 mốc chấm tiến độ
  trong tháng (ngày 15/22/25, khớp với "Ngày chốt V25 = 25/07/2026" ghi ở đầu file) nhưng công thức
  `%V15`/`%V22`/`%V25` và cách tính `Thưởng` tương ứng chưa xác nhận.
- **KH hoạt động - ASO** (`Khoán ASO`, `Số lượng ASO`, `% ASO`): "ASO" viết tắt của gì chưa rõ
  (Active Sales Outlet? Account Sales Officer?). Công thức `% ASO` thử `Số lượng ASO / Khoán ASO`
  cho TDV Đặng Trường Lol: 3/8 = 0.375, báo cáo ghi 0.38 — GẦN khớp nhưng không tuyệt đối trùng,
  có thể do làm tròn khác hoặc công thức khác — cần xác nhận trước khi tin dùng.
- **KPI KH mới**: `Khoán KH mới`, `TH KH mới`, `Trọng số KPI KH mới (%)` — chưa đủ dòng dữ liệu để
  kiểm chứng công thức trọng số.
- **KPI 60% TDV đạt từ 70% DS** (`Số lượng NS`, `SL TDV đạt DS`, `Trọng số KPI NS (%)`): "NS" viết
  tắt của gì chưa rõ (Nhân sự?). Ý nghĩa tên KPI gợi ý đây là chỉ tiêu tập thể (yêu cầu ≥60% TDV
  trong nhóm đạt ≥70% doanh số cá nhân), nhưng công thức tính điểm/trọng số chưa xác nhận.
- **KPI KH Active**: `Khoán KH Active`, `TH KH Active`, `% KH Active`, `Trọng số KPI KH Active (%)`.
- **Đi đúng tuyến** (`Số lượng Call`, `% Thực hiện Call`): có vẻ là KPI riêng, độc lập, không có cột
  trọng số/thưởng đi kèm rõ ràng trong file — chưa rõ có tính vào lương cuối cùng hay chỉ để theo dõi.
- **Công thức lương cuối cùng**: cách `Lương cơ bản`, `Phụ cấp`, `Ăn ca`, và tổng các `Trọng số KPI
  (%)` của từng nhóm cộng lại thành lương thực nhận — hoàn toàn chưa xác nhận, cần DNH cung cấp công
  thức gốc (nhiều khả năng nằm trong 1 file Excel có công thức, không chỉ dữ liệu tĩnh dạng CSV).

## Việc cần làm trước khi bật rule cho chatbot

1. Xác nhận với DNH từng công thức "CHƯA XÁC ĐỊNH" ở trên — ưu tiên hỏi trực tiếp người phụ trách
   lương kinh doanh (không tự suy luận thêm từ dữ liệu, rủi ro sai lương).
2. Sau khi có công thức xác nhận, thiết kế bảng lưu trữ (Bravo có nguồn gốc hay chỉ tồn tại ở Excel
   nội bộ DNH?) và ETL tương ứng — hiện `warehouse.db` không có nguồn nào chứa SKU/khách tái đơn/
   khách active/SP trọng tâm/ASO.
3. Chỉ sau đó mới viết tool chuẩn (`report_templates.py`) hoặc cập nhật `schema_context.py` để AI
   trả lời được câu hỏi KPI lương — tuyệt đối không bật trước khi có nguồn dữ liệu thật, tránh AI bịa
   số ảnh hưởng tới lương thật của nhân viên.
