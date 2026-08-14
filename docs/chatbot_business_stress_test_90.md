# Bộ 90 câu hỏi stress test nghiệp vụ chatbot DNH

> Kỳ kiểm chứng chính: 07/2026 (đã chốt). CTKM: 12/2025 vì liên kết DMS hiện mới phủ đến 09/01/2026.
> Công nợ đọc `warehouse.db/fact_congno_khachhang`, là snapshot chuẩn hóa từ SP gốc DNH.
> Chạy SQL bằng `python scripts/business_stress_suite.py --execute --case Q001`.

## Doanh thu

| ID | Vai trò | Câu hỏi | Checker | Tiêu chí chính |
|---|---|---|---|---|
| Q001 | c_level | Tháng 7/2026 doanh thu thực thuần của OTC, ETC và toàn công ty là bao nhiêu; mỗi kênh có bao nhiêu hóa đơn? | `REV_CHANNEL` | Khớp doanh thu và số hóa đơn từng kênh; tổng bằng OTC + ETC. |
| Q002 | c_level | So với tháng 6/2026, doanh thu tháng 7/2026 tăng hay giảm bao nhiêu tiền và bao nhiêu phần trăm? | `REV_COMPARE` | Khớp hai kỳ trọn tháng và công thức chênh lệch. |
| Q003 | manager | Ngày nào trong tháng 7 có doanh thu cao nhất và thấp nhất; chênh nhau bao nhiêu? | `REV_DAILY` | Lấy cực trị từ đúng doanh thu từng ngày. |
| Q004 | tp | Tuần nào trong tháng 7 đóng góp doanh thu lớn nhất và chiếm bao nhiêu phần trăm tháng? | `REV_WEEK` | Tổng các tuần khớp doanh thu tháng, nêu rõ tuần cắt qua đầu/cuối tháng. |
| Q005 | c_level | Cơ cấu doanh thu tháng 7 theo ba miền và theo OTC/ETC thế nào? | `REV_REGION` | Không làm mất khách chưa xác định vùng; tổng vùng khớp tổng công ty. |
| Q006 | manager | Miền nào phụ thuộc ETC nhiều nhất trong tháng 7? | `REV_REGION` | Tỷ trọng ETC/tổng miền tính từ cùng một kỳ. |
| Q007 | c_level | Giá trị hóa đơn bình quân và hóa đơn lớn nhất tháng 7 của từng kênh là bao nhiêu? | `REV_INVOICE_STATS` | Tính ở cấp hóa đơn, không lấy trung bình dòng hàng. |
| Q008 | manager | Các hóa đơn điều chỉnh hoặc hoàn trong tháng 7 làm giảm doanh thu từng kênh bao nhiêu? | `REV_RETURNS` | Bao gồm Amount9 âm/DocCode HC; không dùng view bỏ mất điều chỉnh. |
| Q009 | tp | Top 20 nhà phân phối theo doanh thu tháng 7, tách theo kênh? | `REV_DISTRIBUTOR` | Thứ hạng và doanh thu khớp SQL. |
| Q010 | c_level | Doanh thu tháng 7 theo từng chi nhánh và kênh; chi nhánh nào lớn nhất? | `REV_BRANCH` | Không nhầm chi nhánh với vùng khách hàng. |
| Q011 | manager | Dữ liệu hóa đơn OTC và ETC mới nhất đang đến ngày nào, đồng bộ lúc nào? | `REV_FRESHNESS` | Phải nêu riêng business date và sync time. |
| Q012 | c_level | Đối soát doanh thu tháng 7 giữa view tổng và view thường: lệch bao nhiêu và nên tin nguồn nào? | `REV_RECONCILE` | Chọn view Total làm nguồn chuẩn và giải thích dòng HC/điều chỉnh. |
## Đội ngũ

| ID | Vai trò | Câu hỏi | Checker | Tiêu chí chính |
|---|---|---|---|---|
| Q013 | tp | Xếp hạng toàn bộ nhân viên theo tỷ lệ hoàn thành chỉ tiêu tháng 7, kèm doanh số, target và số khách phụ trách. | `KPI_EMPLOYEE` | Không cộng trùng target theo khách hàng. |
| Q014 | tp | Đội của quản lý nào có tỷ lệ hoàn thành tháng 7 cao nhất? | `KPI_MANAGER` | Gộp đúng nhân viên theo ManagerCode. |
| Q015 | qlv | Trong đội tôi, ai đạt 100% chỉ tiêu, ai đạt KPI 80%, ai mới chỉ qua cổng thưởng nhóm hàng? | `KPI_THRESHOLDS` | Phân biệt rõ ba mốc 100/80/65-70. |
| Q016 | manager | Bao nhiêu TDV chưa có quản lý trực tiếp trong dữ liệu tháng 7? | `KPI_QUALITY` | Không trả doanh thu 0 thay cho lỗi thiếu ManagerCode. |
| Q017 | manager | Những nhân viên nào có doanh số nhưng không có chỉ tiêu tháng 7? | `KPI_QUALITY` | Liệt kê target rỗng/0 và doanh số thực tế. |
| Q018 | qlv | Top 10 ngày bán hàng tốt nhất của đội trong tháng 7 là những ngày nào? | `KPI_TEAM_DAILY` | Gộp đúng nhân viên vào ManagerCode qua DMSId rồi mới xếp hạng theo ngày. |
| Q019 | tp | So sánh số khách mới, khách mua lại và khách hoạt động của từng nhân viên cuối tháng 7. | `KPI_CUSTOMER_FLAGS` | Dùng trực tiếp IsNC/IsRO/IsAC, không suy diễn. |
| Q020 | manager | Nhân viên nào đang xuất hiện trùng hoặc là bản ghi bóng trong danh mục nhân sự? | `KPI_DUPLICATE` | Nêu IsDuplicate/IsResigned, không đưa bản ghi bóng vào xếp hạng. |
| Q021 | c_level | Vì sao không được cộng doanh số tất cả dòng TP, QLV, TDV trong bảng lương để ra doanh thu công ty? | `KPI_LAYER_RECON` | Chỉ ra các tầng roll-up chồng nhau bằng số thật. |
| Q022 | tp | Tổng target và doanh số của các đội dưới quyền tháng 7 là bao nhiêu, đội nào dưới 80%? | `KPI_MANAGER` | Target đội không bị nhân theo số khách. |
| Q023 | qlv | Trong đội tôi ai có nhiều khách phụ trách nhưng tỷ lệ hoàn thành thấp nhất? | `KPI_EMPLOYEE` | So sánh đồng thời customer count và achievement. |
| Q024 | manager | Có trường hợp một nhân viên vừa thiếu target vừa thiếu quản lý không? | `KPI_QUALITY` | Trả đúng danh sách giao của hai điều kiện. |
## Khách hàng & sản phẩm

| ID | Vai trò | Câu hỏi | Checker | Tiêu chí chính |
|---|---|---|---|---|
| Q025 | manager | Top 20 khách hàng doanh thu lớn nhất tháng 7 là ai? | `CUS_TOP` | Khớp mã, tên và doanh thu; OTC+ETC chỉ cộng một lần. |
| Q026 | tp | Khách hàng doanh thu ít nhất 100 triệu trong 3 tháng gần đây nhưng giảm mạnh so với 3 tháng trước là ai? | `CUS_TREND` | So hai giai đoạn cùng độ dài 05-07 và 02-04. |
| Q027 | qlv | Khách từng mua trong quý II nhưng không phát sinh mua hàng tháng 7 là ai? | `CUS_STOPPED` | Không gọi đây là dự báo rời bỏ; chỉ mô tả dữ liệu lịch sử. |
| Q028 | manager | Cuối tháng 7 có bao nhiêu khách mới, mua lại và hoạt động; doanh thu từng nhóm? | `CUS_ACTIVITY` | Dùng cờ KPI gốc, không suy ra IsRO từ IsNC. |
| Q029 | c_level | Top 10 khách hàng chiếm bao nhiêu phần trăm doanh thu toàn công ty tháng 7? | `CUS_CONCENTRATION` | Tử và mẫu cùng kỳ/cùng nguồn. |
| Q030 | qlv | Khách nào có giá trị đơn bình quân cao nhưng số SKU mỗi đơn thấp? | `CUS_BASKET` | Tính theo cấp đơn, chỉ hàng bán thật UnitPrice>0. |
| Q031 | manager | Top 20 sản phẩm tháng 7 theo doanh thu và số lượng bán thật? | `PRD_TOP` | Loại số lượng hàng giá 0 khỏi PaidQuantity. |
| Q032 | manager | Top 10 sản phẩm OTC và top 10 ETC có khác nhau thế nào? | `PRD_CHANNEL` | Xếp hạng riêng từng kênh. |
| Q033 | c_level | Nhóm sản phẩm nào đóng góp doanh thu lớn nhất và có bao nhiêu mã hàng bán ra? | `PRD_GROUP` | Khớp GroupCode, doanh thu và số mã. |
| Q034 | manager | Những cặp sản phẩm nào thường được mua cùng một đơn nhất trong tháng 7? | `PRD_CROSSSELL` | Ghép theo OrderKey có cả kênh, không tạo cặp A-A hoặc đếm đôi A-B/B-A. |
| Q035 | qlv | Trong top khách tháng 7, khách nào không có tên trong danh mục DMS? | `CUS_TOP` | Giữ mã khách mồ côi và hiển thị thiếu tên thay vì loại khỏi doanh thu. |
| Q036 | manager | Sản phẩm nào có doanh thu cao nhưng số lượng bán thật thấp, cho thấy giá trị mỗi đơn vị cao? | `PRD_TOP` | So doanh thu với PaidQuantity, không tính hàng tặng. |
## Công nợ

| ID | Vai trò | Câu hỏi | Checker | Tiêu chí chính |
|---|---|---|---|---|
| Q037 | c_level | Tổng dư nợ, nợ quá hạn và tỷ lệ quá hạn hiện tại của OTC và ETC? | `DEBT_SUMMARY` | Dùng snapshot SP gốc DNH; nêu thời điểm snapshot. |
| Q038 | manager | Miền nào có tổng nợ quá hạn cao nhất và tỷ lệ quá hạn bao nhiêu? | `DEBT_AREA` | Không cộng tỷ lệ phần trăm trực tiếp. |
| Q039 | manager | Top 30 khách hàng nợ quá hạn lớn nhất hiện tại? | `DEBT_TOP` | Gộp mọi dòng/kênh theo customer_code trước khi xếp hạng. |
| Q040 | c_level | Cơ cấu nợ quá hạn 1-15, 16-30, 31-45 và trên 45 ngày theo từng kênh? | `DEBT_AGING` | Tổng bốn bucket khớp total_overdue. |
| Q041 | manager | Tìm khách đồng thời doanh thu lớn, nợ quá hạn cao và sức mua giảm. | `DEBT_RISK` | Một truy vấn tổng hợp; kỳ 05-07 so 02-04, ngưỡng 100m/50m. |
| Q042 | qlv | Khách nợ quá hạn trong phạm vi của tôi đang nằm chủ yếu ở nhóm tuổi nào? | `DEBT_DETAIL` | Khi test bằng tài khoản QLV phải bị ép phạm vi đội/vùng. |
| Q043 | manager | Khách nào có tỷ lệ nợ quá hạn trên dư nợ cao nhất? | `DEBT_TOP` | Không chia cho 0; phân biệt số tuyệt đối với tỷ lệ. |
| Q044 | c_level | Có bao nhiêu khách vừa bán OTC vừa ETC và tổng nợ của họ thế nào? | `DEBT_DETAIL` | Gộp theo mã khách nhưng vẫn nêu breakdown kênh. |
| Q045 | manager | Snapshot công nợ được cập nhật lúc nào; có dấu hiệu cũ hoặc lệch thời gian giữa các dòng không? | `DEBT_QUALITY` | min/max snapshot phải nhất quán, cảnh báo nếu quá cũ. |
| Q046 | manager | Có dòng công nợ nào tổng bốn nhóm tuổi không bằng tổng quá hạn không? | `DEBT_QUALITY` | broken_aging_sum phải bằng 0. |
| Q047 | manager | Có bao nhiêu dòng công nợ thiếu mã khách hoặc thiếu vùng? | `DEBT_QUALITY` | Nêu số thiếu, không âm thầm bỏ dòng. |
| Q048 | c_level | Nếu tổng nợ quá hạn cao nhưng tập trung ở vài khách, top 10 chiếm bao nhiêu? | `DEBT_TOP` | Tính top 10 sau khi gộp khách và so với DEBT_SUMMARY. |
## KPI

| ID | Vai trò | Câu hỏi | Checker | Tiêu chí chính |
|---|---|---|---|---|
| Q049 | c_level | Toàn công ty tháng 7 có bao nhiêu người đạt đủ 100% chỉ tiêu? | `KPI_THRESHOLDS` | Dùng mốc 100%, không gọi 65/70 hoặc 80 là đạt chỉ tiêu. |
| Q050 | c_level | Bao nhiêu người đạt KPI 80% nhưng chưa đạt đủ chỉ tiêu 100%? | `KPI_THRESHOLDS` | Lấy giao [80%,100%). |
| Q051 | manager | Bao nhiêu TDV đã qua cổng thưởng nhóm hàng 65% nhưng chưa đạt KPI 80%? | `KPI_THRESHOLDS` | Chỉ TDV dùng 65%. |
| Q052 | manager | Bao nhiêu QLV/cấp quản lý qua cổng thưởng nhóm hàng 70% nhưng chưa đạt KPI 80%? | `KPI_THRESHOLDS` | Vai trò quản lý dùng 70%. |
| Q053 | tp | Top 20 nhân viên theo tỷ lệ hoàn thành tháng 7; ai có target bằng 0 phải tách riêng. | `KPI_EMPLOYEE` | Không xếp hạng phần trăm khi target 0. |
| Q054 | tp | 20 nhân viên có tỷ lệ hoàn thành thấp nhất nhưng vẫn có doanh số? | `KPI_EMPLOYEE` | Lọc Actual>0, Target>0 và xếp tăng dần. |
| Q055 | qlv | Doanh số từng ngày của nhân viên tốt nhất đội trong tháng 7 có ngày nào bằng 0? | `KPI_DAILY` | SQL chỉ trả ngày có phát sinh; ngày 0 cần calendar nếu kết luận. |
| Q056 | manager | Đội nào có nhiều khách hoạt động nhất nhưng tỷ lệ hoàn thành thấp hơn 80%? | `KPI_CUSTOMER_FLAGS` | Kết hợp active customers với KPI đội. |
| Q057 | manager | Nhân viên nào có nhiều khách mới nhưng doanh số thấp hơn trung vị đội? | `KPI_CUSTOMER_FLAGS` | Không đánh đồng số khách mới với doanh số. |
| Q058 | c_level | Tổng doanh số theo tầng TP, QLV và nhân viên tuyến dưới có bằng nhau không; vì sao không cộng các tầng? | `KPI_LAYER_RECON` | Nêu rõ roll-up chồng tầng. |
| Q059 | manager | Có nhân viên trùng mã nào làm nguy cơ đếm KPI hai lần không? | `KPI_DUPLICATE` | Đối chiếu cờ duplicate/resigned. |
| Q060 | qlv | Nếu một TDV đạt 67%, phải mô tả trạng thái thưởng nhóm hàng, KPI và chỉ tiêu thế nào? | `KPI_THRESHOLDS` | Đúng: qua 65%, chưa KPI 80%, chưa chỉ tiêu 100%. |
| Q061 | manager | Nếu một QLV đạt 67%, họ đã qua cổng thưởng nhóm hàng chưa? | `KPI_THRESHOLDS` | Đúng: chưa qua cổng 70%; không nói đạt KPI. |
| Q062 | c_level | Nhân viên nào thiếu quan hệ quản lý khiến chatbot không thể xác định đúng đội? | `KPI_QUALITY` | Phải báo thiếu dữ liệu tổ chức, không trả đội doanh thu 0. |
## Lương thưởng

| ID | Vai trò | Câu hỏi | Checker | Tiêu chí chính |
|---|---|---|---|---|
| Q063 | manager | Chi tiết thưởng kinh doanh và phụ cấp tháng 7 của từng nhân viên gồm những khoản nào? | `SALARY_DETAIL` | Không gọi đây là tổng lương/tổng thu nhập vì thiếu LCB. |
| Q064 | c_level | Top 30 nhân viên có tổng thưởng kinh doanh cao nhất tháng 7? | `SALARY_RANK` | TotalBonus chỉ gồm DM+V15+V22+V25+ASO. |
| Q065 | manager | Ai có thưởng V15 cao nhất, tỷ lệ V15 và số tiền đã chốt là bao nhiêu? | `SALARY_PROGRESS` | Phân biệt tỷ lệ với bonus đã lưu. |
| Q066 | manager | Ai có thưởng V22 cao nhất, tỷ lệ V22 và số tiền đã chốt là bao nhiêu? | `SALARY_PROGRESS` | Phân biệt tỷ lệ với bonus đã lưu. |
| Q067 | manager | Ai có thưởng V25 cao nhất, tỷ lệ V25 và số tiền đã chốt là bao nhiêu? | `SALARY_PROGRESS` | Phân biệt tỷ lệ với bonus đã lưu. |
| Q068 | manager | Thưởng ASO của từng nhân viên tháng 7 được chốt thế nào; ai không qua điều kiện nào? | `SALARY_ASO` | ASO là chỉ tiêu/khoản thưởng, không phải chức danh. |
| Q069 | c_level | Tỷ lệ nhân viên có phát sinh V15, V22, V25 và ASO theo vùng/chức danh? | `SALARY_ACHIEVEMENT` | Mẫu số là số nhân viên cùng snapshot. |
| Q070 | manager | Các bậc tiền thưởng V25 tháng 7 theo vùng và chức danh là gì? | `SALARY_RULES` | Đọc DIM_BacThuong đúng hiệu lực. |
| Q071 | manager | Công thức V25 dùng doanh số nào, target nào và ngày chốt nào? | `SALARY_PROGRESS` | Dùng V25Amount/MonthSaleTarget và V25Date thực tế. |
| Q072 | c_level | Có ai tỷ lệ V25 nằm trong bậc có thưởng nhưng V25Bonus đã lưu bằng 0 không? | `SALARY_V25_MISMATCH` | Phải báo chênh lệch, không tự ghi đè số lương. |
| Q073 | manager | Thưởng danh mục DM1/DM2/DM3 và TotalPoint của từng người khớp nhau thế nào? | `SALARY_DETAIL` | Đối chiếu DMBonus với các Amount*Percent và TotalPoint. |
| Q074 | manager | Phụ cấp ăn ca, xăng xe, điện thoại tháng 7 của từng người và tổng phụ cấp? | `SALARY_DETAIL` | Chỉ cộng ba khoản phụ cấp, không nhập vào tiền thưởng. |
| Q075 | c_level | Bảng hiện có đủ dữ liệu để kết luận tổng thu nhập đã gồm lương cơ bản chưa? | `SALARY_LCB_SCHEMA` | Nếu thiếu mapping LCB phải nói rõ chưa đủ. |
| Q076 | manager | Snapshot nào là kỳ lương đã chốt; có dòng đầu/giữa tháng rỗng dễ bị lấy nhầm không? | `SALARY_SNAPSHOTS` | Chỉ dùng cuối tháng đã chốt cho báo cáo lương. |
## Khuyến mãi

| ID | Vai trò | Câu hỏi | Checker | Tiêu chí chính |
|---|---|---|---|---|
| Q077 | c_level | Đánh giá hiệu quả từng chương trình khuyến mãi theo doanh thu gắn với đơn, khách tham gia và số đơn. | `PROMO_EFFECT` | Dùng chuỗi DMS thật; không group ghi chú CTKM hóa đơn. |
| Q078 | manager | Chương trình nào tháng 12/2025 có nhiều khách tham gia nhất? | `PROMO_EFFECT` | Xếp theo Customers, không theo số dòng link. |
| Q079 | manager | Chương trình nào có doanh thu gắn với đơn cao nhưng ít khách tham gia? | `PROMO_EFFECT` | Nêu associated revenue và giới hạn không phải ROI. |
| Q080 | manager | Mỗi chương trình có những khách nào tham gia nhiều đơn nhất? | `PROMO_CUSTOMERS` | Gộp distinct OrderId theo chương trình và khách. |
| Q081 | manager | Số sản phẩm điều kiện, sản phẩm tặng và tổng lượt tặng của từng chương trình? | `PROMO_PRODUCTS` | Phân biệt configured product và gift product. |
| Q082 | c_level | Có bao nhiêu đơn dùng đồng thời nhiều chương trình; điều đó ảnh hưởng cách cộng doanh thu ra sao? | `PROMO_OVERLAP` | Không cộng ngang associated revenue các CTKM. |
| Q083 | manager | Chuỗi liên kết đơn hàng–khuyến mãi hiện có dữ liệu đến ngày nào? | `PROMO_COVERAGE` | Phải công khai LastLinkedOrderDate. |
| Q084 | c_level | Có bao nhiêu liên kết khuyến mãi mất đơn hàng hoặc mất mã chương trình? | `PROMO_QUALITY` | MissingOrder/MissingProgram phải được nêu rõ. |
## Vận hành dữ liệu

| ID | Vai trò | Câu hỏi | Checker | Tiêu chí chính |
|---|---|---|---|---|
| Q085 | manager | Giá trị và số lượng tồn kho theo chi nhánh hiện tại; chi nhánh nào lớn nhất? | `INV_SUMMARY` | Không gộp B01 sản xuất vào vùng kinh doanh. |
| Q086 | manager | Có sản phẩm nào tồn kho âm hoặc giá trị tồn âm không? | `INV_NEGATIVE` | Liệt kê đúng kho/sản phẩm và giá trị. |
| Q087 | manager | Những đơn tháng 7 nào chậm từ hai ngày trở lên mới xuất hóa đơn? | `ORDER_LAG` | Đối chiếu DMSId và dùng ngày đơn–ngày hóa đơn. |
| Q088 | manager | Những đơn DMS tháng 7 chưa tìm thấy hóa đơn tương ứng là đơn nào và trạng thái gì? | `ORDER_NO_INVOICE` | Không kết luận thất thoát nếu chưa xét trạng thái/sync. |
| Q089 | c_level | Mốc dữ liệu mới nhất của doanh thu, KPI, lương và khuyến mãi đang lệch nhau thế nào? | `SOURCE_FRESHNESS` | Nêu riêng từng nguồn; không dùng mốc mới nhất của nguồn A cho nguồn B. |
| Q090 | c_level | Nguồn nào hiện chưa đủ độ phủ để trả lời dữ liệu mới nhất và chatbot phải cảnh báo ra sao? | `SOURCE_FRESHNESS` | CTKM phải nêu source gap; không thay bằng ghi chú hóa đơn hay dự đoán. |

## SQL ground truth

### REV_CHANNEL — Doanh thu và hóa đơn OTC/ETC tháng 07/2026

Nguồn: `bravo` · Case: Q001

```sql
WITH Sales AS (
    SELECT 'OTC' Channel, Amount9, Stt FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT 'ETC', Amount9, Stt FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
)
SELECT Channel, SUM(Amount9) Revenue, COUNT(DISTINCT Stt) InvoiceCount
FROM Sales GROUP BY Channel
UNION ALL
SELECT 'TOTAL', SUM(Amount9), COUNT(DISTINCT CONCAT(Channel, '|', Stt)) FROM Sales
ORDER BY Channel
```

### REV_COMPARE — So sánh doanh thu 06/2026 và 07/2026

Nguồn: `bravo` · Case: Q002

```sql
WITH Sales AS (
    SELECT DocDate, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-06-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT DocDate, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-06-01' AND DocDate < '2026-08-01'
), M AS (
    SELECT CONVERT(char(7), DocDate, 120) YearMonth, SUM(Amount9) Revenue
    FROM Sales GROUP BY CONVERT(char(7), DocDate, 120)
)
SELECT YearMonth, Revenue,
       Revenue - LAG(Revenue) OVER (ORDER BY YearMonth) Delta,
       100.0 * (Revenue - LAG(Revenue) OVER (ORDER BY YearMonth))
             / NULLIF(LAG(Revenue) OVER (ORDER BY YearMonth), 0) GrowthPct
FROM M ORDER BY YearMonth
```

### REV_DAILY — Doanh thu từng ngày tháng 07/2026

Nguồn: `bravo` · Case: Q003

```sql
WITH Dates AS (
    SELECT CONVERT(date, '2026-07-01') DocDate
    UNION ALL
    SELECT DATEADD(day, 1, DocDate) FROM Dates WHERE DocDate < '2026-07-31'
), Sales AS (
    SELECT DocDate, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT DocDate, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
), Daily AS (
    SELECT DocDate, SUM(Amount9) Revenue FROM Sales GROUP BY DocDate
)
SELECT d.DocDate, ISNULL(s.Revenue, 0) Revenue
FROM Dates d LEFT JOIN Daily s ON s.DocDate=d.DocDate
ORDER BY d.DocDate
OPTION (MAXRECURSION 31)
```

### REV_WEEK — Doanh thu theo tuần trong tháng 07/2026

Nguồn: `bravo` · Case: Q004

```sql
WITH Sales AS (
    SELECT DocDate, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT DocDate, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
)
SELECT DATEPART(ISO_WEEK, DocDate) IsoWeek, MIN(DocDate) FirstSaleDate,
       MAX(DocDate) LastSaleDate, SUM(Amount9) Revenue
FROM Sales GROUP BY DATEPART(ISO_WEEK, DocDate) ORDER BY IsoWeek
```

### REV_REGION — Doanh thu ba miền theo hồ sơ khách hàng

Nguồn: `bravo` · Case: Q005, Q006

Lưu ý: Khách chưa có hồ sơ vùng phải hiện CHUA_XAC_DINH, không được âm thầm loại khỏi tổng.

```sql
WITH PrefixMap AS (
    SELECT Prefix,AreaCode FROM (VALUES
      ('AGI','MN'),('BDI','MT'),('BDU','MN'),('BGI','MB'),('BKA','MB'),('BLI','MN'),
      ('BNI','MB'),('BPH','MN'),('BRV','MN'),('BTH','MN'),('BTR','MN'),('CBA','MB'),
      ('CMA','MN'),('CTH','MN'),('DBI','MB'),('DLA','MT'),('DNA','MT'),('DNI','MN'),
      ('DNO','MT'),('DTH','MN'),('GLA','MT'),('HBI','MB'),('HCM','MN'),('HDU','MB'),
      ('HGI','MB'),('HNA','MB'),('HNO','MB'),('HPH','MB'),('HTI','MB'),('HYE','MB'),
      ('KGI','MN'),('KHO','MT'),('KTU','MT'),('LAN','MN'),('LCA','MB'),('LCH','MB'),
      ('LDO','MT'),('LSO','MB'),('NAN','MB'),('NBI','MB'),('NDI','MB'),('NTH','MT'),
      ('PTH','MB'),('PYE','MT'),('QBI','MT'),('QNA','MT'),('QNG','MT'),('QNI','MB'),
      ('QTI','MT'),('SLA','MB'),('STR','MN'),('TBI','MB'),('TGI','MN'),('THO','MB'),
      ('TNG','MB'),('TNI','MN'),('TQU','MB'),('TTH','MT'),('TVI','MN'),('VLO','MN'),
      ('VPH','MB'),('YBA','MB')
    ) m(Prefix,AreaCode)
), Sales AS (
    SELECT 'OTC' Channel, CustomerCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT 'ETC', CustomerCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
), Located AS (
    SELECT s.Channel, s.Amount9,
           CASE WHEN tp.AreaCode IN ('MB','MB1','MB2') THEN 'MB'
                WHEN tp.AreaCode = 'MT' THEN 'MT'
                WHEN tp.AreaCode = 'MN' THEN 'MN'
                ELSE ISNULL(pm.AreaCode,'CHUA_XAC_DINH') END AreaCode
    FROM Sales s
    LEFT JOIN dbo.DMS_KhachHang kh ON kh.Code=s.CustomerCode
    LEFT JOIN dbo.DIM_TinhThanhPho tp ON tp.CityId=kh.CityId
    LEFT JOIN PrefixMap pm ON pm.Prefix=UPPER(LEFT(s.CustomerCode,3))
)
SELECT AreaCode, Channel, SUM(Amount9) Revenue
FROM Located GROUP BY AreaCode, Channel ORDER BY AreaCode, Channel
```

### REV_INVOICE_STATS — Số hóa đơn và giá trị hóa đơn bình quân

Nguồn: `bravo` · Case: Q007

```sql
WITH Invoice AS (
    SELECT 'OTC' Channel, Stt, SUM(Amount9) Revenue FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01' GROUP BY Stt
    UNION ALL
    SELECT 'ETC', Stt, SUM(Amount9) FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01' GROUP BY Stt
)
SELECT Channel, COUNT(*) InvoiceCount, SUM(Revenue) Revenue,
       AVG(CONVERT(decimal(28,2), Revenue)) AverageInvoiceValue,
       MAX(Revenue) LargestInvoiceValue
FROM Invoice GROUP BY Channel
```

### REV_RETURNS — Doanh thu điều chỉnh/hoàn âm

Nguồn: `bravo` · Case: Q008

```sql
WITH Sales AS (
    SELECT 'OTC' Channel, DocDate, Stt, DocCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT 'ETC', DocDate, Stt, DocCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
)
SELECT Channel, COUNT(DISTINCT Stt) AffectedInvoices, SUM(Amount9) NegativeRevenue
FROM Sales WHERE Amount9 < 0 OR DocCode='HC' GROUP BY Channel
```

### REV_DISTRIBUTOR — Doanh thu theo nhà phân phối

Nguồn: `bravo` · Case: Q009

```sql
WITH Sales AS (
    SELECT 'OTC' Channel, DistributorCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT 'ETC', DistributorCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
)
SELECT TOP (20) DistributorCode, Channel, SUM(Amount9) Revenue
FROM Sales GROUP BY DistributorCode, Channel ORDER BY SUM(Amount9) DESC
```

### REV_BRANCH — Doanh thu theo chi nhánh

Nguồn: `bravo` · Case: Q010

```sql
WITH Sales AS (
    SELECT 'OTC' Channel, BranchCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT 'ETC', BranchCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
)
SELECT BranchCode, Channel, SUM(Amount9) Revenue
FROM Sales GROUP BY BranchCode, Channel ORDER BY BranchCode, Channel
```

### REV_FRESHNESS — Ngày và thời điểm đồng bộ hóa đơn mới nhất

Nguồn: `bravo` · Case: Q011

```sql
SELECT 'OTC' Channel, MAX(DocDate) MaxDocDate, MAX(SyncAt) MaxSyncAt, COUNT_BIG(*) [RowCount]
FROM dbo.vHoaDonTotal
UNION ALL
SELECT 'ETC', MAX(DocDate), MAX(SyncAt), COUNT_BIG(*) FROM dbo.vHoaDonETCTotal
```

### REV_RECONCILE — Đối soát view Total với view thường

Nguồn: `bravo` · Case: Q012

Lưu ý: Doanh thu chuẩn dùng view Total vì view thường có thể thiếu dòng HC/điều chỉnh.

```sql
SELECT 'OTC' Channel,
       (SELECT SUM(Amount9) FROM dbo.vHoaDonTotal WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01') TotalViewRevenue,
       (SELECT SUM(Amount9) FROM dbo.vHoaDon WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01') BaseViewRevenue
UNION ALL
SELECT 'ETC',
       (SELECT SUM(Amount9) FROM dbo.vHoaDonETCTotal WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'),
       (SELECT SUM(Amount9) FROM dbo.vHoaDonETC WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01')
```

### CUS_TOP — Top khách hàng theo doanh thu

Nguồn: `bravo` · Case: Q025, Q035

```sql
WITH Sales AS (
    SELECT CustomerCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT CustomerCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
)
SELECT TOP (20) s.CustomerCode, MAX(kh.Name) CustomerName, SUM(s.Amount9) Revenue
FROM Sales s LEFT JOIN dbo.DMS_KhachHang kh ON kh.Code=s.CustomerCode
GROUP BY s.CustomerCode ORDER BY SUM(s.Amount9) DESC
```

### CUS_TREND — Doanh thu khách hàng giảm giữa hai kỳ ba tháng

Nguồn: `bravo` · Case: Q026

```sql
WITH Sales AS (
    SELECT CustomerCode, DocDate, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-02-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT CustomerCode, DocDate, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-02-01' AND DocDate<'2026-08-01'
), R AS (
    SELECT CustomerCode,
      SUM(CASE WHEN DocDate>='2026-05-01' THEN Amount9 ELSE 0 END) RecentRevenue,
      SUM(CASE WHEN DocDate<'2026-05-01' THEN Amount9 ELSE 0 END) PriorRevenue
    FROM Sales GROUP BY CustomerCode
)
SELECT TOP (20) CustomerCode, RecentRevenue, PriorRevenue,
       100.0*(RecentRevenue-PriorRevenue)/NULLIF(PriorRevenue,0) ChangePct
FROM R WHERE RecentRevenue<PriorRevenue AND RecentRevenue>=100000000
ORDER BY ChangePct, RecentRevenue DESC
```

### CUS_STOPPED — Khách từng mua nhưng không mua trong 07/2026

Nguồn: `bravo` · Case: Q027

```sql
WITH Sales AS (
    SELECT CustomerCode, DocDate, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-04-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT CustomerCode, DocDate, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-04-01' AND DocDate<'2026-08-01'
), R AS (
    SELECT CustomerCode,
      SUM(CASE WHEN DocDate<'2026-07-01' THEN Amount9 ELSE 0 END) PriorRevenue,
      SUM(CASE WHEN DocDate>='2026-07-01' THEN Amount9 ELSE 0 END) JulyRevenue,
      MAX(DocDate) LastPurchaseDate
    FROM Sales GROUP BY CustomerCode
)
SELECT TOP (30) CustomerCode, PriorRevenue, JulyRevenue, LastPurchaseDate
FROM R WHERE PriorRevenue>0 AND JulyRevenue=0 ORDER BY PriorRevenue DESC
```

### CUS_ACTIVITY — Khách mới/mua lại/hoạt động theo snapshot KPI

Nguồn: `bravo` · Case: Q028

```sql
WITH Snap AS (
    SELECT MAX(SaveDate) SaveDate FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31'
)
SELECT IsNC, IsRO, IsAC, COUNT(DISTINCT CustomerCode) CustomerCount,
       SUM(Amount_CT) Revenue
FROM dbo.FACT_TongHopKhachHang
WHERE SaveDate=(SELECT SaveDate FROM Snap)
GROUP BY IsNC, IsRO, IsAC ORDER BY IsNC, IsRO, IsAC
```

### CUS_CONCENTRATION — Mức tập trung doanh thu vào top khách hàng

Nguồn: `bravo` · Case: Q029

```sql
WITH Sales AS (
    SELECT CustomerCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT CustomerCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
), C AS (
    SELECT CustomerCode, SUM(Amount9) Revenue FROM Sales GROUP BY CustomerCode
), R AS (
    SELECT CustomerCode, Revenue, ROW_NUMBER() OVER (ORDER BY Revenue DESC) rn FROM C
)
SELECT SUM(Revenue) TotalRevenue,
       SUM(CASE WHEN rn<=10 THEN Revenue ELSE 0 END) Top10Revenue,
       100.0*SUM(CASE WHEN rn<=10 THEN Revenue ELSE 0 END)/NULLIF(SUM(Revenue),0) Top10SharePct
FROM R
```

### CUS_BASKET — Số SKU và giá trị đơn hàng theo khách

Nguồn: `bravo` · Case: Q030

```sql
WITH Lines AS (
    SELECT CustomerCode, CONCAT('OTC|',Stt) OrderKey, ItemCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' AND UnitPrice>0
    UNION ALL
    SELECT CustomerCode, CONCAT('ETC|',Stt) OrderKey, ItemCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' AND UnitPrice>0
), Orders AS (
    SELECT CustomerCode, OrderKey, COUNT(DISTINCT ItemCode) SKUCount, SUM(Amount9) Revenue
    FROM Lines GROUP BY CustomerCode, OrderKey
)
SELECT TOP (20) CustomerCode, COUNT(*) OrderCount,
       AVG(CONVERT(decimal(18,2), SKUCount)) AvgSKUPerOrder,
       AVG(CONVERT(decimal(28,2), Revenue)) AvgOrderValue
FROM Orders GROUP BY CustomerCode HAVING COUNT(*)>=3 ORDER BY AvgOrderValue DESC
```

### PRD_TOP — Top sản phẩm theo doanh thu và số lượng bán thật

Nguồn: `bravo` · Case: Q031, Q036

```sql
WITH Sales AS (
    SELECT ItemCode, Amount9, Quantity, UnitPrice FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT ItemCode, Amount9, Quantity, UnitPrice FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
)
SELECT TOP (20) s.ItemCode, MAX(p.Name) ProductName, SUM(s.Amount9) Revenue,
       SUM(CASE WHEN ISNULL(s.UnitPrice,0)>0 THEN s.Quantity ELSE 0 END) PaidQuantity
FROM Sales s LEFT JOIN dbo.BRV_SanPham p ON p.Code=s.ItemCode
GROUP BY s.ItemCode ORDER BY SUM(s.Amount9) DESC
```

### PRD_CHANNEL — Sản phẩm theo kênh OTC/ETC

Nguồn: `bravo` · Case: Q032

```sql
WITH Sales AS (
    SELECT 'OTC' Channel, ItemCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT 'ETC', ItemCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
), R AS (
    SELECT Channel, ItemCode, SUM(Amount9) Revenue,
           ROW_NUMBER() OVER (PARTITION BY Channel ORDER BY SUM(Amount9) DESC) rn
    FROM Sales GROUP BY Channel, ItemCode
)
SELECT Channel, ItemCode, Revenue FROM R WHERE rn<=10 ORDER BY Channel, rn
```

### PRD_GROUP — Doanh thu theo nhóm sản phẩm

Nguồn: `bravo` · Case: Q033

```sql
WITH Sales AS (
    SELECT ItemCode, CONVERT(varchar(50),GroupCode) GroupCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT ItemCode, CONVERT(varchar(50),GroupCode) GroupCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
)
SELECT GroupCode, SUM(Amount9) Revenue, COUNT(DISTINCT ItemCode) ProductCount
FROM Sales GROUP BY GroupCode ORDER BY SUM(Amount9) DESC
```

### PRD_CROSSSELL — Cặp sản phẩm thường cùng xuất hiện

Nguồn: `bravo` · Case: Q034

```sql
WITH Lines AS (
    SELECT DISTINCT CONCAT('OTC|',Stt) OrderKey, ItemCode FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' AND UnitPrice>0
    UNION
    SELECT DISTINCT CONCAT('ETC|',Stt), ItemCode FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' AND UnitPrice>0
)
SELECT TOP (20) a.ItemCode ProductA, b.ItemCode ProductB, COUNT_BIG(*) OrdersTogether
FROM Lines a JOIN Lines b ON b.OrderKey=a.OrderKey AND b.ItemCode>a.ItemCode
GROUP BY a.ItemCode,b.ItemCode ORDER BY COUNT_BIG(*) DESC
```

### KPI_EMPLOYEE — KPI nhân viên tại snapshot 31/07/2026

Nguồn: `bravo` · Case: Q013, Q023, Q053, Q054

```sql
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31'),
Agg AS (
  SELECT EmployeeCode, MAX(ManagerCode) ManagerCode, SUM(Amount_CT) Actual,
         MAX(MonthSaleTarget) Target, COUNT(DISTINCT CustomerCode) Customers
  FROM dbo.FACT_TongHopKhachHang WHERE SaveDate=(SELECT d FROM Snap)
  GROUP BY EmployeeCode
)
SELECT a.EmployeeCode, n.Name EmployeeName, n.PositionCode, n.AreaCode, a.ManagerCode,
       a.Actual, a.Target, 100.0*a.Actual/NULLIF(a.Target,0) AchievementPct, a.Customers
FROM Agg a LEFT JOIN dbo.DIM_NhanVien n ON n.EmployeeCode=a.EmployeeCode
ORDER BY AchievementPct DESC
```

### KPI_THRESHOLDS — Ba mốc 100%, 80%, 65/70%

Nguồn: `bravo` · Case: Q015, Q049, Q050, Q051, Q052, Q060, Q061

```sql
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31'),
E AS (
 SELECT EmployeeCode, PositionCode, AreaCode, MonthSaleAmount, MonthSaleTarget, MonthSalePercent_R,
        CASE WHEN PositionCode='TDV' THEN 0.65 ELSE 0.70 END BonusGate
 FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
)
SELECT PositionCode, AreaCode, COUNT(*) Employees,
 SUM(CASE WHEN MonthSalePercent_R>=1.00 THEN 1 ELSE 0 END) Reached100,
 SUM(CASE WHEN MonthSalePercent_R>=0.80 THEN 1 ELSE 0 END) ReachedKPI80,
 SUM(CASE WHEN MonthSalePercent_R>=BonusGate THEN 1 ELSE 0 END) ReachedGroupBonusGate
FROM E GROUP BY PositionCode, AreaCode ORDER BY PositionCode, AreaCode
```

### KPI_MANAGER — Tổng hợp KPI theo quản lý

Nguồn: `bravo` · Case: Q014, Q022

```sql
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31'),
Emp AS (
 SELECT EmployeeCode, MAX(ManagerCode) ManagerCode, SUM(Amount_CT) Actual, MAX(MonthSaleTarget) Target
 FROM dbo.FACT_TongHopKhachHang WHERE SaveDate=(SELECT d FROM Snap) GROUP BY EmployeeCode
)
SELECT ManagerCode, COUNT(*) EmployeeCount, SUM(Actual) TeamActual, SUM(Target) TeamTarget,
       100.0*SUM(Actual)/NULLIF(SUM(Target),0) TeamAchievementPct
FROM Emp WHERE ManagerCode IS NOT NULL GROUP BY ManagerCode ORDER BY TeamAchievementPct DESC
```

### KPI_DAILY — Doanh số thực tế theo ngày và nhân viên

Nguồn: `bravo` · Case: Q055

```sql
WITH Sales AS (
 SELECT DocDate, EmpDMSCode EmployeeDMS, Amount9 FROM dbo.vHoaDonTotal
 WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
 UNION ALL
 SELECT DocDate, EmpDMSCode, Amount9 FROM dbo.vHoaDonETCTotal
 WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
)
SELECT TOP (100) n.EmployeeCode, n.Name EmployeeName, s.DocDate, SUM(s.Amount9) DailyRevenue
FROM Sales s LEFT JOIN dbo.DIM_NhanVien n ON n.DMSId=s.EmployeeDMS
GROUP BY n.EmployeeCode,n.Name,s.DocDate ORDER BY SUM(s.Amount9) DESC
```

### KPI_TEAM_DAILY — Top ngày bán hàng theo từng đội quản lý

Nguồn: `bravo` · Case: Q018

```sql
WITH Snap AS (
 SELECT MAX(SaveDate) d FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31'
), EmpMap AS (
 SELECT EmployeeCode,MAX(EmpDMSCode) EmpDMSCode,MAX(ManagerCode) ManagerCode
 FROM dbo.FACT_TongHopKhachHang WHERE SaveDate=(SELECT d FROM Snap)
 GROUP BY EmployeeCode
), Sales AS (
 SELECT DocDate,EmpDMSCode,SUM(Amount9) Revenue FROM dbo.vHoaDonTotal
 WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' GROUP BY DocDate,EmpDMSCode
 UNION ALL
 SELECT DocDate,EmpDMSCode,SUM(Amount9) Revenue FROM dbo.vHoaDonETCTotal
 WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' GROUP BY DocDate,EmpDMSCode
), TeamDay AS (
 SELECT e.ManagerCode,s.DocDate,SUM(s.Revenue) Revenue
 FROM Sales s JOIN EmpMap e ON e.EmpDMSCode=s.EmpDMSCode
 WHERE NULLIF(e.ManagerCode,'') IS NOT NULL
 GROUP BY e.ManagerCode,s.DocDate
), Ranked AS (
 SELECT ManagerCode,DocDate,Revenue,
        ROW_NUMBER() OVER (PARTITION BY ManagerCode ORDER BY Revenue DESC,DocDate) RankInTeam
 FROM TeamDay
)
SELECT ManagerCode,DocDate,Revenue,RankInTeam
FROM Ranked WHERE RankInTeam<=10 ORDER BY ManagerCode,RankInTeam
```

### KPI_QUALITY — Nhân viên thiếu target hoặc thiếu quản lý

Nguồn: `bravo` · Case: Q016, Q017, Q024, Q062

```sql
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31'),
Emp AS (
 SELECT EmployeeCode, MAX(ManagerCode) ManagerCode, MAX(MonthSaleTarget) Target,
        SUM(Amount_CT) Actual, COUNT(DISTINCT CustomerCode) Customers
 FROM dbo.FACT_TongHopKhachHang WHERE SaveDate=(SELECT d FROM Snap) GROUP BY EmployeeCode
)
SELECT e.EmployeeCode,n.Name,n.PositionCode,e.ManagerCode,e.Target,e.Actual,e.Customers
FROM Emp e LEFT JOIN dbo.DIM_NhanVien n ON n.EmployeeCode=e.EmployeeCode
WHERE ISNULL(e.Target,0)<=0 OR (n.PositionCode='TDV' AND NULLIF(e.ManagerCode,'') IS NULL)
ORDER BY n.PositionCode,e.EmployeeCode
```

### KPI_DUPLICATE — Nhân viên trùng/bóng và trùng snapshot

Nguồn: `bravo` · Case: Q020, Q059

```sql
SELECT EmployeeCode, COUNT(*) DimRows,
       SUM(CASE WHEN IsDuplicate=1 THEN 1 ELSE 0 END) DuplicateFlags,
       SUM(CASE WHEN IsResigned=1 THEN 1 ELSE 0 END) ResignedFlags
FROM dbo.DIM_NhanVien GROUP BY EmployeeCode HAVING COUNT(*)>1 OR MAX(IsDuplicate)=1
ORDER BY COUNT(*) DESC, EmployeeCode
```

### KPI_CUSTOMER_FLAGS — Khách mới, mua lại, hoạt động theo nhân viên

Nguồn: `bravo` · Case: Q019, Q056, Q057

```sql
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31')
SELECT TOP (100) EmployeeCode, MAX(ManagerCode) ManagerCode,
       COUNT(DISTINCT CustomerCode) AssignedCustomers,
       COUNT(DISTINCT CASE WHEN IsNC=1 THEN CustomerCode END) NewCustomers,
       COUNT(DISTINCT CASE WHEN IsRO=1 THEN CustomerCode END) ReorderCustomers,
       COUNT(DISTINCT CASE WHEN IsAC=1 THEN CustomerCode END) ActiveCustomers,
       SUM(Amount_CT) Revenue
FROM dbo.FACT_TongHopKhachHang WHERE SaveDate=(SELECT d FROM Snap)
GROUP BY EmployeeCode ORDER BY Revenue DESC
```

### KPI_LAYER_RECON — Đối soát các tầng KPI không được cộng chồng

Nguồn: `bravo` · Case: Q021, Q058

Lưu ý: Các tầng TP/QLV/TDV đều có roll-up; tuyệt đối không cộng toàn bảng để ra doanh thu công ty.

```sql
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT PositionCode, COUNT(*) Employees, SUM(MonthSaleAmount) SumMonthSaleAmount,
       SUM(MonthSaleTarget) SumMonthSaleTarget
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
GROUP BY PositionCode ORDER BY PositionCode
```

### DEBT_SUMMARY — Tổng công nợ theo kênh

Nguồn: `local` · Case: Q037

```sql
SELECT sales_channel, SUM(balance_end) balance_end, SUM(total_overdue) total_overdue,
       ROUND(100.0*SUM(total_overdue)/NULLIF(SUM(balance_end),0),1) overdue_pct,
       MAX(snapshot_at) snapshot_at
FROM fact_congno_khachhang GROUP BY sales_channel ORDER BY sales_channel
```

### DEBT_AREA — Công nợ theo vùng

Nguồn: `local` · Case: Q038

```sql
SELECT area_code, SUM(balance_end) balance_end, SUM(total_overdue) total_overdue,
       ROUND(100.0*SUM(total_overdue)/NULLIF(SUM(balance_end),0),1) overdue_pct
FROM fact_congno_khachhang GROUP BY area_code ORDER BY total_overdue DESC
```

### DEBT_TOP — Top khách hàng nợ quá hạn

Nguồn: `local` · Case: Q039, Q043, Q048

```sql
SELECT customer_code, MAX(customer_name) customer_name, SUM(balance_end) balance_end,
       SUM(total_overdue) total_overdue,
       ROUND(100.0*SUM(total_overdue)/NULLIF(SUM(balance_end),0),1) overdue_pct
FROM fact_congno_khachhang GROUP BY customer_code
HAVING SUM(total_overdue)>0 ORDER BY total_overdue DESC LIMIT 30
```

### DEBT_AGING — Cơ cấu tuổi nợ

Nguồn: `local` · Case: Q040

```sql
SELECT sales_channel, SUM(overdue_1_15) overdue_1_15,
       SUM(overdue_15_30) overdue_16_30, SUM(overdue_30_45) overdue_31_45,
       SUM(overdue_gt_45) overdue_gt_45,
       SUM(total_overdue) total_overdue
FROM fact_congno_khachhang GROUP BY sales_channel ORDER BY sales_channel
```

### DEBT_RISK — Khách doanh thu lớn, nợ cao và sức mua giảm

Nguồn: `local` · Case: Q041

```sql
WITH sales AS (
 SELECT customer_code, doc_date, amount9 FROM vhoadon_otc
 WHERE doc_date BETWEEN '2026-02-01' AND '2026-07-31'
 UNION ALL
 SELECT customer_code, doc_date, amount9 FROM vhoadon_etc
 WHERE doc_date BETWEEN '2026-02-01' AND '2026-07-31'
), revenue AS (
 SELECT customer_code,
  SUM(CASE WHEN doc_date BETWEEN '2026-05-01' AND '2026-07-31' THEN amount9 ELSE 0 END) recent_revenue,
  SUM(CASE WHEN doc_date BETWEEN '2026-02-01' AND '2026-04-30' THEN amount9 ELSE 0 END) prior_revenue
 FROM sales GROUP BY customer_code
), debt AS (
 SELECT customer_code, MAX(customer_name) customer_name, SUM(balance_end) balance_end,
        SUM(total_overdue) overdue, MAX(snapshot_at) snapshot_at
 FROM fact_congno_khachhang GROUP BY customer_code
)
SELECT r.customer_code,d.customer_name,r.recent_revenue,r.prior_revenue,
       ROUND(100.0*(r.recent_revenue-r.prior_revenue)/NULLIF(r.prior_revenue,0),1) change_pct,
       d.balance_end,d.overdue,d.snapshot_at
FROM revenue r JOIN debt d ON d.customer_code=r.customer_code
WHERE r.recent_revenue>=100000000 AND d.overdue>=50000000 AND r.recent_revenue<r.prior_revenue
ORDER BY d.overdue DESC,r.recent_revenue DESC LIMIT 30
```

### DEBT_DETAIL — Chi tiết công nợ theo khách và kênh

Nguồn: `local` · Case: Q042, Q044

```sql
SELECT customer_code,customer_name,sales_channel,area_code,balance_end,total_overdue,
       overdue_1_15,overdue_15_30,overdue_30_45,overdue_gt_45,snapshot_at
FROM fact_congno_khachhang
WHERE total_overdue>0 ORDER BY total_overdue DESC LIMIT 50
```

### DEBT_QUALITY — Kiểm tra chất lượng snapshot công nợ

Nguồn: `local` · Case: Q045, Q046, Q047

```sql
SELECT COUNT(*) row_count, COUNT(DISTINCT customer_code) customer_count,
       SUM(CASE WHEN customer_code IS NULL OR customer_code='' THEN 1 ELSE 0 END) missing_customer,
       SUM(CASE WHEN area_code IS NULL OR area_code='' THEN 1 ELSE 0 END) missing_area,
       SUM(CASE WHEN ABS(total_overdue-(overdue_1_15+overdue_15_30+overdue_30_45+overdue_gt_45))>1
                THEN 1 ELSE 0 END) broken_aging_sum,
       MIN(snapshot_at) min_snapshot_at,MAX(snapshot_at) max_snapshot_at
FROM fact_congno_khachhang
```

### SALARY_DETAIL — Chi tiết thưởng và phụ cấp theo nhân viên

Nguồn: `bravo` · Case: Q063, Q073, Q074

```sql
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT TOP (300) EmployeeCode,EmployeeName,PositionCode,AreaCode,ManagerCode,SaveDate,
       MonthSaleAmount,MonthSaleTarget,MonthSalePercent_R,
       DM1Amount,DM1Percent_R,DM2Amount,DM2Percent_R,DM3Amount,DM3Percent_R,DMBonus,TotalPoint,
       V15Bonus,V22Bonus,V25Bonus,ASOBonus,LunchAmount_R,TransportAmount_R,PhoneAmount_R
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
ORDER BY EmployeeCode
```

### SALARY_RANK — Xếp hạng tổng thưởng kinh doanh

Nguồn: `bravo` · Case: Q064

Lưu ý: TotalBonus chưa gồm lương cơ bản.

```sql
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT TOP (30) EmployeeCode,EmployeeName,PositionCode,AreaCode,MonthSalePercent_R,
       DMBonus,V15Bonus,V22Bonus,V25Bonus,ASOBonus,
       ISNULL(DMBonus,0)+ISNULL(V15Bonus,0)+ISNULL(V22Bonus,0)+ISNULL(V25Bonus,0)+ISNULL(ASOBonus,0) TotalBonus,
       ISNULL(LunchAmount_R,0)+ISNULL(TransportAmount_R,0)+ISNULL(PhoneAmount_R,0) Allowance
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
ORDER BY TotalBonus DESC
```

### SALARY_PROGRESS — Thưởng V15/V22/V25 theo số đã chốt

Nguồn: `bravo` · Case: Q065, Q066, Q067, Q071

```sql
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT TOP (300) EmployeeCode,EmployeeName,PositionCode,AreaCode,
       V15Date,V15Amount,V15Percent_R,V15Bonus,
       V22Date,V22Amount,V22Percent_R,V22Bonus,
       V25Date,V25Amount,V25Percent_R,V25Bonus
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
ORDER BY V25Bonus DESC,V22Bonus DESC,V15Bonus DESC
```

### SALARY_ASO — Thưởng ASO và điều kiện đã chốt

Nguồn: `bravo` · Case: Q068

```sql
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT TOP (300) EmployeeCode,EmployeeName,PositionCode,AreaCode,ASOCalType,
       ActiveCusQuantity,ActiveCusTarget,ACPercent_R,ASOQuantity,ASOPercent_R,ASOBonus,
       PassCheckASOForASO,PassCheckSaleForASO,PassCheckASOBonus
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
ORDER BY ASOBonus DESC,ASOPercent_R DESC
```

### SALARY_ACHIEVEMENT — Số người có thưởng V15/V22/V25/ASO

Nguồn: `bravo` · Case: Q069

```sql
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT PositionCode,AreaCode,COUNT(*) Employees,
       SUM(CASE WHEN V15Bonus>0 THEN 1 ELSE 0 END) V15Achieved,
       SUM(CASE WHEN V22Bonus>0 THEN 1 ELSE 0 END) V22Achieved,
       SUM(CASE WHEN V25Bonus>0 THEN 1 ELSE 0 END) V25Achieved,
       SUM(CASE WHEN ASOBonus>0 THEN 1 ELSE 0 END) ASOAchieved
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
GROUP BY PositionCode,AreaCode ORDER BY PositionCode,AreaCode
```

### SALARY_RULES — Bậc thưởng đang hiệu lực

Nguồn: `bravo` · Case: Q070

```sql
SELECT TypeCode,AreaCode,PositionCode,Description,StartDate,EndDate,
       FromValue,ToValue,Earn1,Earn2,EarnMax,CheckASO,CheckTargetEmp,ASOCusCondType
FROM dbo.DIM_BacThuong
WHERE TypeCode IN ('V15','V22','V25','ASO')
  AND StartDate<='2026-07-01' AND (EndDate IS NULL OR EndDate>='2026-07-31')
ORDER BY TypeCode,AreaCode,PositionCode,BuildInOrder
```

### SALARY_V25_MISMATCH — V25 đạt bậc nhưng số đã lưu bằng 0

Nguồn: `bravo` · Case: Q072

```sql
SELECT TOP (50) f.EmployeeCode,f.EmployeeName,f.AreaCode,f.PositionCode,f.SaveDate,
       f.V25Date,f.V25Amount,f.MonthSaleTarget,f.V25Percent_R,f.V25Bonus
FROM dbo.FACT_ThongKeTinhLuong f
WHERE f.SaveDate='2026-07-31' AND f.V25Percent_R>0.7 AND ISNULL(f.V25Bonus,0)=0
AND EXISTS (
 SELECT 1 FROM dbo.DIM_BacThuong b
 WHERE b.TypeCode='V25' AND b.AreaCode=f.AreaCode AND b.PositionCode=f.PositionCode
   AND b.StartDate<='2026-07-01' AND (b.EndDate IS NULL OR b.EndDate>='2026-07-31')
   AND ISNULL(b.Earn1,0)>0
   AND f.V25Percent_R>=ISNULL(b.FromValue,0)/100.0
   AND f.V25Percent_R<ISNULL(b.ToValue,3000)/100.0
)
ORDER BY f.V25Percent_R DESC
```

### SALARY_SNAPSHOTS — Snapshot lương đã chốt và dòng giữa kỳ

Nguồn: `bravo` · Case: Q076

```sql
SELECT SaveDate,COUNT(*) Employees,
       SUM(CASE WHEN V25Percent_R IS NULL THEN 1 ELSE 0 END) MissingV25Percent,
       SUM(CASE WHEN MonthSaleTarget<=0 OR MonthSaleTarget IS NULL THEN 1 ELSE 0 END) MissingTarget
FROM dbo.FACT_ThongKeTinhLuong
WHERE SaveDate>='2026-06-01' AND SaveDate<'2026-09-01'
GROUP BY SaveDate ORDER BY SaveDate
```

### SALARY_LCB_SCHEMA — Kiểm tra có/không dữ liệu lương cơ bản

Nguồn: `bravo` · Case: Q075

Lưu ý: Không được gọi tổng thưởng + phụ cấp là tổng thu nhập nếu chưa có mapping Level -> LCB.

```sql
SELECT c.name ColumnName,t.name DataType
FROM sys.columns c JOIN sys.types t ON t.user_type_id=c.user_type_id
WHERE c.object_id=OBJECT_ID('dbo.FACT_ThongKeTinhLuong')
  AND (c.name LIKE '%Luong%' OR c.name LIKE '%Salary%' OR c.name LIKE '%Level%')
ORDER BY c.column_id
```

### PROMO_COVERAGE — Mức phủ liên kết đơn hàng–CTKM

Nguồn: `bravo` · Case: Q083

```sql
SELECT MIN(h.DocDate) FirstLinkedOrderDate,MAX(h.DocDate) LastLinkedOrderDate,
       COUNT_BIG(*) LinkRows,COUNT(DISTINCT x.OrderId) LinkedOrders,
       COUNT(DISTINCT x.ProgId) Programs,MAX(x.SyncAt) LastLinkSyncAt
FROM dbo.DMS_DonHangCTKM x LEFT JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
```

### PROMO_EFFECT — Hiệu quả CTKM tháng 12/2025

Nguồn: `bravo` · Case: Q077, Q078, Q079

Lưu ý: AssociatedRevenue không cộng ngang giữa các CTKM vì một đơn có thể gắn nhiều chương trình.

```sql
WITH ProgramOrders AS (
 SELECT x.ProgId,x.OrderId,MAX(h.CustomerCode) CustomerCode
 FROM dbo.DMS_DonHangHdr h JOIN dbo.DMS_DonHangCTKM x ON x.OrderId=h.Id
 WHERE h.DocDate>='2025-12-01' AND h.DocDate<'2026-01-01'
 GROUP BY x.ProgId,x.OrderId
), InvoiceByOrder AS (
 SELECT TRY_CONVERT(int,DMSId) OrderId,SUM(Amount9) Revenue
 FROM dbo.vHoaDonTotal
 WHERE DocDate>='2025-12-01' AND DocDate<'2026-01-01' AND TRY_CONVERT(int,DMSId) IS NOT NULL
 GROUP BY TRY_CONVERT(int,DMSId)
)
SELECT p.Id ProgramId,p.Code ProgramCode,p.Name ProgramName,
       COUNT_BIG(*) Orders,COUNT(DISTINCT po.CustomerCode) Customers,
       SUM(ISNULL(i.Revenue,0)) AssociatedRevenue,
       SUM(CASE WHEN i.OrderId IS NULL THEN 1 ELSE 0 END) OrdersWithoutInvoice
FROM ProgramOrders po JOIN dbo.DMS_CTKM p ON p.Id=po.ProgId
LEFT JOIN InvoiceByOrder i ON i.OrderId=po.OrderId
GROUP BY p.Id,p.Code,p.Name ORDER BY AssociatedRevenue DESC
```

### PROMO_CUSTOMERS — Khách hàng tham gia từng CTKM

Nguồn: `bravo` · Case: Q080

```sql
SELECT TOP (100) p.Code ProgramCode,p.Name ProgramName,h.CustomerCode,
       COUNT(DISTINCT x.OrderId) Orders
FROM dbo.DMS_DonHangCTKM x JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
JOIN dbo.DMS_CTKM p ON p.Id=x.ProgId
WHERE h.DocDate>='2025-12-01' AND h.DocDate<'2026-01-01'
GROUP BY p.Code,p.Name,h.CustomerCode ORDER BY Orders DESC
```

### PROMO_PRODUCTS — Sản phẩm điều kiện và hàng tặng CTKM

Nguồn: `bravo` · Case: Q081

```sql
WITH Gifts AS (
 SELECT ProgId,COUNT(DISTINCT NULLIF(ItemCode,'')) GiftProducts,
        SUM(CONVERT(bigint,ISNULL(SlotQuantity,0))) GiftSlots
 FROM dbo.DMS_DonHangCTKM GROUP BY ProgId
), Configured AS (
 SELECT t.ProgId,COUNT(DISTINCT NULLIF(d.ItemId,'')) ConfiguredProducts
 FROM dbo.DMS_CTKMOnTop1 t JOIN dbo.DMS_DKKMCt d ON d.CondId=t.CondId GROUP BY t.ProgId
)
SELECT p.Code,p.Name,ISNULL(c.ConfiguredProducts,0) ConfiguredProducts,
       ISNULL(g.GiftProducts,0) GiftProducts,ISNULL(g.GiftSlots,0) GiftSlots
FROM dbo.DMS_CTKM p LEFT JOIN Gifts g ON g.ProgId=p.Id LEFT JOIN Configured c ON c.ProgId=p.Id
ORDER BY GiftSlots DESC
```

### PROMO_OVERLAP — Đơn hàng dùng nhiều CTKM

Nguồn: `bravo` · Case: Q082

```sql
SELECT TOP (50) x.OrderId,h.DocDate,h.CustomerCode,COUNT(DISTINCT x.ProgId) ProgramCount,
       STRING_AGG(CONVERT(varchar(max),p.Code),', ') ProgramCodes
FROM dbo.DMS_DonHangCTKM x JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
JOIN dbo.DMS_CTKM p ON p.Id=x.ProgId
WHERE h.DocDate>='2025-12-01' AND h.DocDate<'2026-01-01'
GROUP BY x.OrderId,h.DocDate,h.CustomerCode HAVING COUNT(DISTINCT x.ProgId)>1
ORDER BY ProgramCount DESC
```

### PROMO_QUALITY — Chất lượng liên kết CTKM

Nguồn: `bravo` · Case: Q084

```sql
SELECT COUNT_BIG(*) LinkRows,
       SUM(CASE WHEN h.Id IS NULL THEN 1 ELSE 0 END) MissingOrder,
       SUM(CASE WHEN p.Id IS NULL THEN 1 ELSE 0 END) MissingProgram,
       COUNT(DISTINCT CASE WHEN h.Id IS NOT NULL AND p.Id IS NOT NULL THEN x.Id END) ValidLinks,
       MAX(h.DocDate) LastLinkedOrderDate
FROM dbo.DMS_DonHangCTKM x LEFT JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
LEFT JOIN dbo.DMS_CTKM p ON p.Id=x.ProgId
```

### INV_SUMMARY — Tồn kho theo chi nhánh

Nguồn: `bravo` · Case: Q085

```sql
SELECT k.BranchCode,COUNT(DISTINCT t.ItemId) ProductCount,
       SUM(t.Quantity) Quantity,SUM(t.Amount) InventoryValue
FROM dbo.BRV_TonKhoDK t LEFT JOIN dbo.BRV_Kho k ON k.Id=t.WarehouseId
WHERE t.IsActive=1 GROUP BY k.BranchCode ORDER BY k.BranchCode
```

### INV_NEGATIVE — Tồn kho âm hoặc giá trị bất thường

Nguồn: `bravo` · Case: Q086

```sql
SELECT TOP (100) k.BranchCode,k.Code WarehouseCode,t.ItemId,p.Code ItemCode,p.Name ProductName,
       t.Quantity,t.Amount
FROM dbo.BRV_TonKhoDK t LEFT JOIN dbo.BRV_Kho k ON k.Id=t.WarehouseId
LEFT JOIN dbo.BRV_SanPham p ON p.Id=t.ItemId
WHERE t.IsActive=1 AND (t.Quantity<0 OR t.Amount<0)
ORDER BY ABS(t.Amount) DESC
```

### ORDER_LAG — Độ trễ tạo đơn DMS đến hóa đơn

Nguồn: `bravo` · Case: Q087

```sql
SELECT TOP (100) h.Id OrderId,h.DocDate OrderDate,MIN(v.DocDate) InvoiceDate,h.CustomerCode,
       DATEDIFF(day,h.DocDate,MIN(v.DocDate)) LagDays,SUM(v.Amount9) Revenue
FROM dbo.DMS_DonHangHdr h JOIN dbo.vHoaDonTotal v ON TRY_CONVERT(int,v.DMSId)=h.Id
WHERE h.DocDate>='2026-07-01' AND h.DocDate<'2026-08-01'
GROUP BY h.Id,h.DocDate,h.CustomerCode
HAVING ABS(DATEDIFF(day,h.DocDate,MIN(v.DocDate)))>=2
ORDER BY ABS(DATEDIFF(day,h.DocDate,MIN(v.DocDate))) DESC
```

### ORDER_NO_INVOICE — Đơn DMS chưa tìm thấy hóa đơn

Nguồn: `bravo` · Case: Q088

```sql
SELECT TOP (100) h.Id OrderId,h.DocDate,h.CustomerCode,h.StatusId,h.StatusDescription,h.IsSync,h.SKUQuantity
FROM dbo.DMS_DonHangHdr h
WHERE h.DocDate>='2026-07-01' AND h.DocDate<'2026-08-01'
AND NOT EXISTS (SELECT 1 FROM dbo.vHoaDonTotal v WHERE TRY_CONVERT(int,v.DMSId)=h.Id)
ORDER BY h.DocDate DESC,h.Id DESC
```

### SOURCE_FRESHNESS — Mốc dữ liệu mới nhất của các nguồn chính

Nguồn: `bravo` · Case: Q089, Q090

```sql
SELECT 'vHoaDonTotal' SourceName,MAX(DocDate) BusinessDate,MAX(SyncAt) SyncAt FROM dbo.vHoaDonTotal
UNION ALL SELECT 'vHoaDonETCTotal',MAX(DocDate),MAX(SyncAt) FROM dbo.vHoaDonETCTotal
UNION ALL SELECT 'FACT_TongHopKhachHang',MAX(SaveDate),MAX(CreatedAt) FROM dbo.FACT_TongHopKhachHang
UNION ALL SELECT 'FACT_ThongKeTinhLuong',MAX(SaveDate),MAX(CreatedAt) FROM dbo.FACT_ThongKeTinhLuong
UNION ALL SELECT 'DMS_DonHangCTKM',MAX(h.DocDate),MAX(x.SyncAt)
FROM dbo.DMS_DonHangCTKM x LEFT JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
```
