# Báo cáo công việc 27/08–09/09/2026 theo lịch sử commit

Ngày chốt: 09/09/2026, múi giờ UTC+7. Dự án: DNH × MCNA — Chatbot Dược Nam Hà.

## 1. Phạm vi và cách đọc báo cáo

Báo cáo liệt kê đầy đủ **86 commit** có trong lịch sử `master` từ 27/08 đến 09/09/2026, chốt tại `9c370e8`. Mỗi commit có ngày giờ, diễn giải công việc, tên commit gốc, danh sách file và đường dẫn kiểm tra trên GitHub. Commit tạo chính báo cáo tổng hợp này không nằm trong mẫu 86 commit, để tránh tự đếm báo cáo vào kết quả phát triển.

Đã kiểm tra các nhánh local/remote hiện có và fetch origin trước khi tổng hợp; trong khoảng này danh sách commit của master và toàn bộ refs đang có cùng 86 commit. Phạm vi không bao gồm nhánh chưa được fetch hoặc thao tác trên máy 24 không được lưu vào Git. Thời gian tác giả và thời gian commit của 86 bản ghi trùng nhau.

Các bản ghi dùng tài khoản tác giả Git `nssiwi19`; một số có đồng tác giả trong commit body. Báo cáo phản ánh công việc của cả dự án, không lấy tên tài khoản Git làm bằng chứng ai trực tiếp thao tác trong từng phiên.

**Trạng thái “đã commit” chứng minh thay đổi đã lưu trong repository.** Xác nhận đã deploy, số liệu đúng trên Bravo, tester chấm đạt và nghiệm thu là những bằng chứng riêng. Các số đo trích commit bên dưới là kết quả tại thời điểm được ghi, không phải đo lại trong lượt viết báo cáo.

## 2. Tổng quan công việc

- **86 commit**, tác động **86 file**, trong đó **33 file kiểm thử**.
- **65 commit** có thay đổi file trong `tests/`; đây là số commit có test, không phải số câu UAT đạt.
- So sánh trạng thái trước commit đầu kỳ với `9c370e8`: **16.871 dòng thêm, 882 dòng xóa**. Số này gồm code, SQL, test và tài liệu.
- Các khối chính: 7 file backend; 8 file src; 13 script; 16 tài liệu docs; 33 file test; 4 file trong cây frontend và 5 file cấu hình/đầu ra còn lại.
- Các ngày 29/08–02/09 và 06/09 không có commit trong lịch sử được kiểm tra. Không suy từ đó rằng không có hoạt động kiểm thử hoặc vận hành.

| Ngày | Số commit | Công việc chính |
|---|---:|---|
| 27/08/2026 | 18 | Teams; snapshot KPI; báo cáo QLV ngày/tuần/tháng; đối chiếu đội; IsAC/ASO. |
| 28/08/2026 | 6 | Email; nhãn vai trò; quyền ETC; độ phủ test; gói SQL/Excel bàn giao UAT. |
| 03/09/2026 | 2 | Đối chiếu 40 công cụ và Bravo; sửa checker; ghi nhận giới hạn nguồn và rủi ro dữ liệu. |
| 04/09/2026 | 16 | Tồn kho hai hệ/năm tài chính; roster đội; mẫu số KPI; V25; CreatedAt; kế hoạch và checker. |
| 05/09/2026 | 2 | Xếp hạng KPI đầu tháng; nhân sự thiếu dữ liệu; khóa kỳ báo cáo. |
| 07/09/2026 | 19 | Định tuyến C/M/V; đối chiếu doanh thu; target đội; hành vi khách; bán chéo; đơn DMS; đi tuyến. |
| 08/09/2026 | 9 | Tồn kho/SKU; giới hạn CTKM/thu tiền; bảo vệ bộ chạy eval; YTD và giới hạn nguồn. |
| 09/09/2026 | 14 | Vá smoke C31/M20/V33; V38/V39; C20/C28/C29/C54; giao việc và kiểm tra Antigravity. |
| **Tổng** | **86** | Toàn bộ commit chi tiết ở mục 6. |

## 3. Kết quả theo nhóm công việc

### 3.1 Báo cáo tự động và giao diện

Đã xây và hoàn thiện báo cáo QLV hằng ngày, hằng tuần, hằng tháng; giữ phạm vi theo đội và bổ sung gửi email. Đã sửa định dạng danh sách email, nội dung card Teams và nhãn vai trò Trưởng phòng/Giám đốc miền. Giao diện được sửa lỗi lint Next 16. Cây `frontend/` được gắn cảnh báo không dùng làm root; chưa có thao tác xóa cây này trong các commit được tổng hợp.

Commit tiêu biểu: `83ca375`, `ad368f6`, `3da1877`, `a4c70c3`, `67c7297`, `331b7b9`, `516525b`, `79ee98e`, `be8ca86`.

### 3.2 Doanh thu, đội ngũ và KPI

Đã sửa lấy snapshot theo tháng/từng người, loại lẫn tầng tổng hợp kênh với đội QLV, tách nhân viên chưa bán khỏi việc xác định danh sách đội, hợp roster kỳ tròn và kỳ mới. Đã sửa xếp hạng KPI trả rỗng đầu tháng, giữ CTV và ngưỡng thưởng phù hợp, khôi phục target đội và báo rõ người thiếu dữ liệu.

Các đường báo cáo được bổ sung giới hạn khi dùng thành phần đội hiện tại cho kỳ lịch sử, khi thiếu kế hoạch năm hoặc khi đối chiếu doanh thu còn chênh chưa giải thích. Chênh lệch chưa có bằng chứng không được tự gọi là bình thường.

Commit tiêu biểu: `0705c4e`, chuỗi đối chiếu QLV ngày 27/08, `eb8d373`, `77162d9`, `a957a48`, `c32a405`, `d5d0559`, `9398bd1`, `3ac1135`, `4eb8890`, `efd02b2`, `8281fa1`.

### 3.3 Tồn kho và SKU

Đã nạp/lọc năm tài chính để tránh cộng nhiều năm tồn đầu kỳ; bổ sung hệ kho sản xuất và phân biệt hệ kinh doanh; sửa nhãn kho B01. Bổ sung báo cáo nguy cơ thiếu hàng, mức tồn so tốc độ bán, SKU tồn cao/chậm bán và khách từng mua liên quan; chỉnh định tuyến V38/V39 để tập trung đúng nhóm SKU.

Số tồn đầu kỳ, khả năng cấp hàng hiện tại và nhu cầu khách thực tế cần giữ đúng định nghĩa nguồn. Danh sách khách từng mua chỉ hỗ trợ liên hệ; lịch sử mua không xác nhận khách đang có đơn chờ hay doanh thu chắc chắn mất.

Commit tiêu biểu: `eb8d373`, `519db18`, `74df6b5`, `ea76f53`, `c34730c`, `f512987`.

### 3.4 Khách hàng, tăng trưởng và phân công

Đã tách IsAC khỏi ASO; mở rộng định tuyến hành vi khách, ưu tiên khách, cơ cấu SKU và bán chéo. Đã bổ sung chuỗi khách hàng theo hóa đơn, cố định phạm vi OTC cho C29, giữ cờ NC/RO theo nguồn Bravo và ổn định cửa sổ lịch sử khi tính tái kích hoạt.

Các cụm C20/C28 được bổ sung đối chiếu và giới hạn về thay đổi phân công. Bộ checker được sửa ánh xạ để phân biệt đếm khách, phân rã tăng trưởng, cohort, khách tương đồng và dịch chuyển nhân sự.

Commit tiêu biểu: `f5c0081`, `700ad9f`, `d3626be`, `6e75e23`, `fbe55c5`, `52636dd`, `98abacb`, `fbcf9f5`, `94d444a`, `78e8030`.

### 3.5 Đơn hàng, đi tuyến và định nghĩa nghiệp vụ

Đã gỡ suy luận gian lận từ chênh CreatedAt/DocDate sau khi DNH xác nhận hai mốc thuộc hai giai đoạn khác nhau. Các đợt sau bổ sung đối chiếu đơn DMS với hóa đơn, số ngoại lệ và phần giao nhau giữa đơn hủy/chưa hóa đơn/chênh ngày. Có thêm báo cáo hiệu quả đi tuyến từ DMS_DiTuyen.

Chênh ngày tạo đơn–hóa đơn không chứng minh ngày giao hàng trễ; phải có mốc giao thực tế mới đánh giá được giao chậm.

Commit tiêu biểu: `1e91e37`, `b586adc`, `d0393ca`, `e64d9eb`, `faf7f65`, `d28531c`, `644fef1`.

### 3.6 Phân quyền, lương thưởng và chất lượng dữ liệu

Đã củng cố phạm vi ETC, phạm vi QLV/miền và các lớp kiểm trong quá trình trả lời. Giữ quyền chặn lương/thưởng cá nhân chi tiết đối với vai Giám đốc miền/kênh; không coi quyền bị chặn là đã đối chiếu được thưởng thực chi. Đã cập nhật quy tắc V15/V22/V25 và chặn kết luận thiếu căn cứ về KPI đầu tháng.

C54 được sửa theo roster đầy đủ, ranh giới nhân viên/cấp quản lý và mốc ngày lịch sử. Sau các commit đó vẫn còn ghi nhận UAT về danh sách thiếu target bị lặp; cần giữ phần này trong backlog.

Commit tiêu biểu: `9fb2288`, `6853da5`, `2d38cdc`, `57a245a`, `28719bb`, `8202085`, `29da152`.

### 3.7 Công cụ kiểm chứng, chi phí và bàn giao UAT

Đã tạo bộ SQL đối chứng và Excel tracking 138 câu, công cụ chạy SQL, đối chiếu snapshot–hóa đơn, script kiểm scope/tài khoản/tồn kho và bộ bất biến mở rộng 40 công cụ. Đã sửa checker sai nội dung hoặc gán sai câu; ghi rõ CTKM, thu tiền và các nguồn chưa hỗ trợ.

Bộ chạy 138 câu được ẩn API key và dừng khi nhà cung cấp báo lỗi tài khoản. Đây là các biện pháp vận hành có commit; không có số tổng chi phí API hai tuần được đối chiếu trong lượt này.

Commit tiêu biểu: `d30a0d8`, `79ee98e`, `47c0e3b`, `700ad9f`, `c79517b`, `c7c1075`, `2215bb4`, `07c7438`, `1081be4`, `3da7744`, `c28f2ba`.

## 4. Bằng chứng kiểm thử và giới hạn khi báo cáo

| Mốc | Bằng chứng lịch sử | Cách sử dụng |
|---|---|---|
| 27/08 | Commit `0705c4e` ghi 370 test xanh sau vá Teams/snapshot | Mốc lịch sử của bộ kiểm thử lúc đó. |
| 03/09 | Commit `47c0e3b` ghi 435 test đạt, 87 checker biên dịch, parse đủ 138 câu và sinh 368.226 dòng đáp án | Chứng minh công việc kiểm bộ SQL; không đồng nghĩa 138 câu chatbot đạt. |
| 04/09 | Commit `77162d9` ghi 448 test, 58 bất biến đạt; `ea76f53` ghi 452 test | Mốc kiểm chứng các đợt vá roster/tồn kho theo ghi nhận commit. |
| 09/09 | Handoff `dc90454` ghi baseline gần nhất 516 passed, 1 deselected | Kết quả được ghi trong handoff; chưa chạy lại toàn bộ test trong lượt tổng hợp này. |
| Bản M16 đang dở | Báo cáo `9c370e8` ghi 12 test mục tiêu đạt | Bản local chưa hoàn tất xử lý kỳ MTD, chưa đủ cơ sở chốt UAT. |

Số **59/138 (42,8%)** là số được ghi trong báo cáo chốt phiên `9c370e8`, không phải số vừa tính lại từ Google Sheet. Lượt này không đọc lại các cột E/I/J hoặc xác minh toàn bộ tài khoản test; do đó không dùng số này làm tỷ lệ UAT cập nhật theo thời gian thực.

Nếu báo tỷ lệ trên mẫu đã loại câu bị chặn theo yêu cầu sau đó, phải tính lại hợp các câu đạt, khử trùng mã câu và nêu rõ số câu loại cùng mẫu số còn lại. Không chuyển số commit, số checker READY hoặc số test tự động thành tỷ lệ trả lời đúng.

Chưa có bằng chứng được tổng hợp trong lượt này để công bố mốc trên 95% cho đủ 138 câu. Với mẫu cố định 138 câu, mốc trên 95% là ít nhất 132 câu đạt, có kết quả retest đúng vai và người chấm xác nhận.

## 5. Công việc chưa chốt tại thời điểm báo cáo

| Phần | Trạng thái | Việc còn lại đã ghi nhận |
|---|---|---|
| M16/S55 | Bản thử local trong hai file backend và một file test | Xử lý tháng MTD trước khi đếm chuỗi giảm; đối chiếu danh sách và retest đúng vai. |
| S67/S40 của phiên Antigravity | Diff checker local, chưa được nhận | Rà retention, phạm vi khách QLV, duplicate mapping; ngưỡng im lặng cần đúng quyết định nghiệp vụ. |
| C54/S38 | Có ba commit vá; phản hồi danh sách thiếu target còn lặp | Dedupe danh sách hiển thị, tách cờ có doanh số thiếu target, retest. |
| V06/V07 | Có code liên quan đã sửa | Đối chiếu khóa đơn và cùng kỳ/scope trên dữ liệu thật. |
| V21/C30/C34/C44 | Còn hạng mục trong handoff | Kiểm danh sách đầy đủ, giới hạn lịch sử khách mới, ngày bán đầu tiên/target SKU và khóa hợp đồng. |
| M20 và các câu M | Quyền lương vẫn được giữ; còn yêu cầu xác nhận đầy đủ câu trả lời | Retest bằng tài khoản Giám đốc miền/kênh, không dùng lượt QLV để chốt kết quả M. |
| Dữ liệu DNH | Có phát hiện CTKM ngừng đồng bộ, thiếu nguồn thu tiền/cam kết và định nghĩa cần xác nhận | DNH xác nhận/cung cấp nguồn; chỉ kết luận trong phần dữ liệu có bằng chứng. |

Bốn file tracked đang dở được giữ tại máy: `backend/nl2sql.py`, `backend/report_templates.py`, `tests/test_cat_danh_sach_chuoi_thang.py`, `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md`. Nội dung này chưa được đưa vào commit hoàn tất hay tính là đã triển khai.

Đợt công bố tài liệu gồm handoff `dc90454`, báo cáo chốt phiên `9c370e8` và báo cáo tổng hợp này. Push Git không xác nhận máy 24 đã kéo code hoặc restart dịch vụ.

## 6. Nhật ký đầy đủ từng commit

Mỗi đường dẫn commit mở đúng bản thay đổi trên GitHub. Danh sách file lấy từ Git; mục kiểm thử ghi các file test có sửa trong commit, không suy đoán rằng toàn bộ test đã chạy thành công.

### 27/08/2026 — 18 commit

Teams; snapshot KPI; báo cáo QLV ngày/tuần/tháng; đối chiếu đội; IsAC/ASO.

#### 01. 09:29:52 — [83ca375](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/83ca3757ca4665c3296ce87d0b24e6809a8f5607)

Sửa thông báo Teams về Adaptive Card 1.4; thay Table bằng FactSet/TextBlock và phân biệt webhook đã nhận với tin đã hiển thị trên Teams.

- Tên commit: fix(teams): hạ Adaptive Card 1.5 → 1.4, gỡ Table — master chưa từng nhận bản vá 04/08.
- File triển khai/tài liệu: `src/notifier.py`.
- File kiểm thử thay đổi: `tests/test_teams_adaptive_card_1_4.py`, `tests/test_teams_dinh_tuyen_nguoi_nhan.py`.

#### 02. 09:30:26 — [0705c4e](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/0705c4e45b59abc1f9dd79c58ed961c79e2d2420)

Sửa bốn đường lấy KPI dùng snapshot theo tháng và theo từng nhân viên/khách, tránh mất cả vùng khi Bravo ghi các miền vào ngày khác nhau.

- Tên commit: fix(kpi): gộp snapshot Bravo theo THÁNG thay vì ghim MAX(SaveDate) — 4 điểm, không phải 2.
- File triển khai/tài liệu: `src/alerts.py`, `src/etl.py`.
- File kiểm thử thay đổi: `tests/test_kpi_gop_theo_thang.py`.

#### 03. 09:49:15 — [ad368f6](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/ad368f67d30f9e6ba1f7e31a61c918d8d927a3b3)

Củng cố nội dung gửi Teams và cách tổng hợp KPI; bổ sung script kiểm snapshot M4 cùng kiểm thử.

- Tên commit: fix: harden Teams payloads and KPI rollups.
- File triển khai/tài liệu: `scripts/verify_m4_kpi_snapshot.py`, `src/alerts.py`, `src/notifier.py`.
- File kiểm thử thay đổi: `tests/test_kpi_gop_theo_thang.py`, `tests/test_teams_adaptive_card_1_4.py`.

#### 04. 10:52:08 — [3da1877](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/3da187763c18c19b3f41934c7ee6f9f7b97b58ed)

Xây báo cáo QLV hằng ngày theo đúng đội: cấu hình, lấy dữ liệu, gửi thông báo và script đối chiếu.

- Tên commit: feat: add team-scoped QLV daily digest.
- File triển khai/tài liệu: `config/config.yaml`, `main.py`, `scripts/verify_qlv_digest_reconciliation.py`, `src/notifier.py`, `src/qlv_digest.py`.
- File kiểm thử thay đổi: `tests/test_qlv_digest.py`, `tests/test_teams_dinh_tuyen_nguoi_nhan.py`.

#### 05. 10:56:11 — [d0cf669](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/d0cf669717934bacaef08cfd9c1178ea5581aa5a)

Bổ sung chạy thử báo cáo QLV không gửi thật và kiểm tra phạm vi dữ liệu trước khi vận hành.

- Tên commit: test: add QLV dry-run and scope validation.
- File triển khai/tài liệu: `scripts/dry_run_qlv_digest.py`, `scripts/verify_qlv_digest_reconciliation.py`, `src/qlv_digest.py`.
- File kiểm thử thay đổi: `tests/test_qlv_digest.py`.

#### 06. 11:01:27 — [afdfeec](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/afdfeec3c2cf144962c1d5ecad8ba70022341bb7)

Tự tìm danh sách đội QLV để chạy đối chiếu chỉ đọc, giảm phụ thuộc danh sách khai báo thủ công.

- Tên commit: feat: discover QLV teams for read-only reconciliation.
- File triển khai/tài liệu: `scripts/verify_qlv_digest_reconciliation.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 07. 11:02:19 — [fef32d3](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/fef32d3f634ecc57a03fd2dfba32aaf93ac4021b)

Thêm kiểm thử cho việc tự tìm QLV, khóa hành vi của chức năng vừa bổ sung.

- Tên commit: test: cover automatic QLV discovery.
- File kiểm thử thay đổi: `tests/test_qlv_digest.py`.

#### 08. 11:11:30 — [3fa8ac3](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/3fa8ac3a9692b6c017addacb889f96f05f28613a)

Loại dòng tổng hợp cấp kênh khỏi danh sách QLV để tránh coi tổng kênh là một đội.

- Tên commit: fix: exclude channel rollups from QLV discovery.
- File triển khai/tài liệu: `scripts/verify_qlv_digest_reconciliation.py`.
- File kiểm thử thay đổi: `tests/test_qlv_digest.py`.

#### 09. 11:16:30 — [fabab9c](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/fabab9c3c5cd10f9f7d79fea6cd1817bac758bca)

Tách phép đối chiếu tổng kênh khỏi phép đối chiếu đội QLV.

- Tên commit: fix: reconcile channel rollups separately from QLV teams.
- File triển khai/tài liệu: `scripts/verify_qlv_digest_reconciliation.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 10. 11:24:27 — [e769744](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/e7697448bcbf0771dc4c8b74db5de7d8d8919426)

Tìm quản lý theo snapshot của từng nhân viên, xử lý dữ liệu được ghi lệch ngày.

- Tên commit: fix: discover QLV managers per employee snapshot.
- File triển khai/tài liệu: `scripts/verify_qlv_digest_reconciliation.py`.
- File kiểm thử thay đổi: `tests/test_qlv_digest.py`.

#### 11. 11:29:22 — [577bef5](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/577bef54376dd23567f721c5ef19fef9a65e211f)

Bổ sung nhận diện dòng tổng hợp dùng mã kênh trong phép đối chiếu QLV.

- Tên commit: fix: include channel-code rollups in QLV reconciliation.
- File triển khai/tài liệu: `scripts/verify_qlv_digest_reconciliation.py`.
- File kiểm thử thay đổi: `tests/test_qlv_digest.py`.

#### 12. 11:35:08 — [df56a9d](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/df56a9d72af882ed766450d39b159b729704efc9)

Chấp nhận mã quản lý làm khóa tổng hợp kênh trong script đối chiếu.

- Tên commit: fix: accept manager code as channel rollup key.
- File triển khai/tài liệu: `scripts/verify_qlv_digest_reconciliation.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 13. 11:36:51 — [9f61f42](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/9f61f42870eeb84f766575f80d5a51a28ca30fc7)

Thêm script chỉ đọc để truy nguyên phần chênh lệch doanh thu khi đối chiếu QLV.

- Tên commit: feat: add read-only QLV reconciliation gap diagnostics.
- File triển khai/tài liệu: `scripts/diagnose_qlv_reconciliation_gaps.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 14. 11:49:36 — [1e06888](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/1e068880a8978658cab2d739c68ecd396af03899)

Đối chiếu QLV với đúng tập TDV tương ứng, tránh so hai phạm vi khác nhau.

- Tên commit: fix: reconcile QLV against matching TDV scope.
- File triển khai/tài liệu: `scripts/verify_qlv_digest_reconciliation.py`.
- File kiểm thử thay đổi: `tests/test_qlv_digest.py`.

#### 15. 12:34:39 — [005ec3c](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/005ec3c616e209692df4e5db6a19e1146ae84bdf)

Loại TDV không còn hoạt động khỏi phép đối chiếu báo cáo QLV.

- Tên commit: fix: exclude inactive TDVs from QLV reconciliation.
- File triển khai/tài liệu: `scripts/verify_qlv_digest_reconciliation.py`.
- File kiểm thử thay đổi: `tests/test_qlv_digest.py`.

#### 16. 16:09:43 — [a4c70c3](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/a4c70c3683122cc1d63e455f58149cec5c81d4d4)

Bổ sung báo cáo QLV hằng tuần và hằng tháng theo phạm vi đội.

- Tên commit: feat: add scoped QLV weekly and monthly reports.
- File triển khai/tài liệu: `main.py`, `src/qlv_digest.py`.
- File kiểm thử thay đổi: `tests/test_qlv_digest.py`.

#### 17. 16:23:26 — [67c7297](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/67c72976e03bc3b25b6c7dec8f782bcae3f5d22a)

Hoàn thiện đường gửi báo cáo QLV tuần/tháng qua email.

- Tên commit: fix: send QLV weekly monthly reports by email.
- File triển khai/tài liệu: `main.py`, `src/qlv_digest.py`.
- File kiểm thử thay đổi: `tests/test_qlv_digest.py`.

#### 18. 16:44:24 — [f5c0081](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/f5c0081c1ff340417faf71a86e8aeb8b762655ed)

Tách chỉ số cờ IsAC khỏi ASO; cập nhật dữ liệu đồng bộ, công cụ báo cáo, mô tả nghiệp vụ và kiểm thử lương/khách hàng.

- Tên commit: fix: separate is_ac metrics from ASO.
- File triển khai/tài liệu: `backend/docs_chinh_sach_thu_nhap_TDV_OTC.md`, `backend/local_warehouse.py`, `backend/nl2sql.py`, `backend/report_templates.py`, `backend/schema_context.py`, `backend/sync_warehouse.py`, `docs/Cau_hoi_can_DNH_xac_nhan.md`, `docs/bao_cao_tien_do_27-08.md`.
- File kiểm thử thay đổi: `tests/test_customer_lifecycle.py`, `tests/test_salary_detail.py`.

### 28/08/2026 — 6 commit

Email; nhãn vai trò; quyền ETC; độ phủ test; gói SQL/Excel bàn giao UAT.

#### 19. 08:16:35 — [331b7b9](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/331b7b91d7264e24823a540f53779a2b8614a404)

Sửa định dạng danh sách trong email báo cáo QLV.

- Tên commit: fix: clean QLV email list formatting.
- File triển khai/tài liệu: `src/qlv_digest.py`.
- File kiểm thử thay đổi: `tests/test_qlv_digest.py`.

#### 20. 08:31:26 — [516525b](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/516525b987cdb5ac51649a09d9e43ac5bafed8a6)

Tách xếp hạng sản phẩm theo kênh và thống nhất nhãn vai trò tiếng Việt; thay đổi có mặt ở cả src/ và frontend/src/.

- Tên commit: fix: split channel product rankings and unify role labels.
- File triển khai/tài liệu: `backend/nl2sql.py`, `frontend/src/app/AdminUsersPanel.tsx`, `frontend/src/app/page.tsx`, `frontend/src/app/roleLabels.ts`, `src/app/AdminUsersPanel.tsx`, `src/app/page.tsx`, `src/app/roleLabels.ts`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`.

#### 21. 09:15:07 — [9fb2288](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/9fb228898cc2e5f0172dcf665f2d145dda6ab602)

Siết phạm vi ETC đối xứng giữa các đường báo cáo; bổ sung kiểm thử khách hàng, doanh thu kênh, tồn kho và phạm vi QLV.

- Tên commit: fix: enforce symmetric ETC channel scopes.
- File triển khai/tài liệu: `backend/report_templates.py`, `docs/kiem_tra_nghiep_vu_28-08.md`.
- File kiểm thử thay đổi: `tests/test_customer_detail.py`, `tests/test_management_periods_inventory.py`, `tests/test_qlv_unblocked_area_only_tools.py`, `tests/test_revenue_by_channel.py`.

#### 22. 09:17:30 — [6853da5](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/6853da5ef34922bdd13215e4ae5947fa47513e58)

Thêm script kiểm quyền ETC trên production theo chế độ chỉ đọc.

- Tên commit: test: add read-only ETC production verifier.
- File triển khai/tài liệu: `docs/kiem_tra_nghiep_vu_28-08.md`, `scripts/verify_etc_channel_scope.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 23. 09:27:34 — [77022a7](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/77022a7a882910ba4e3fba023b2fe85c446bbf3e)

Bổ sung kiểm thử gọi trực tiếp các công cụ báo cáo còn thiếu độ phủ và cập nhật tài liệu kiểm tra nghiệp vụ.

- Tên commit: test: complete direct coverage for reporting tools.
- File triển khai/tài liệu: `backend/report_templates.py`, `docs/kiem_tra_nghiep_vu_28-08.md`.
- File kiểm thử thay đổi: `tests/test_remaining_tool_coverage.py`.

#### 24. 16:47:12 — [d30a0d8](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/d30a0d828ab4b082759dff69fe57a56aabfff0ab)

Tạo gói bàn giao UAT: bộ SQL đối chứng, công cụ chạy 138 câu SQL, đối chiếu snapshot–hóa đơn, file Excel tracking và hướng dẫn tester.

- Tên commit: feat: add chatbot UAT validation and handoff pack.
- File triển khai/tài liệu: `.gitignore`, `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_month_by_month.md`, `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md`, `docs/huong_dan_ban_giao_uat.md`, `outputs/uat_chatbot_dnh/uat_tracking_chatbot_dnh.xlsx`, `scripts/chay_sql_doi_chung_138.py`, `scripts/doi_chieu_snapshot_vs_hoadon.py`.
- File kiểm thử thay đổi: `tests/test_sql_doi_chung_138.py`.

### 03/09/2026 — 2 commit

Đối chiếu 40 công cụ và Bravo; sửa checker; ghi nhận giới hạn nguồn và rủi ro dữ liệu.

#### 25. 09:39:21 — [79ee98e](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/79ee98e22ac9cf6f85ba63a921004e7cd6371dab)

Hoàn thiện baseline UAT, mở rộng đối chiếu 40 công cụ, kiểm tài khoản thiếu phạm vi; cập nhật Excel và đánh dấu cây frontend/ không dùng làm root.

- Tên commit: test: hoan thien baseline UAT va doi chieu 40 tool.
- File triển khai/tài liệu: `.gitignore`, `backend/report_templates.py`, `docs/Nhom_A_can_DNH_chot_truoc_UAT_10-09-2026.md`, `docs/backlog_tu_phan_hoi_nguoi_dung.md`, `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_month_by_month.md`, `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md`, `docs/huong_dan_ban_giao_uat.md`, `docs/tracking_hoan_thien_du_an_03-30_09_2026.md`, `frontend/_KHONG_DUNG_LAM_ROOT_DIRECTORY.md`, `outputs/uat_chatbot_dnh/uat_tracking_chatbot_dnh.xlsx`, `scripts/chay_sql_doi_chung_138.py`, `scripts/doi_chieu_so_lieu_tool_moi.py`, `scripts/kiem_tai_khoan_thieu_pham_vi.py`.
- File kiểm thử thay đổi: `tests/test_customer_lifecycle.py`, `tests/test_doi_chieu_40_tools.py`, `tests/test_forecast_va_scope.py`, `tests/test_kiem_tai_khoan_thieu_pham_vi.py`, `tests/test_sql_doi_chung_138.py`.

#### 26. 16:38:42 — [47c0e3b](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/47c0e3b44abfa3fe6bd4c114b31cbfa373e30814)

Soát 22 câu UAT với Bravo theo ghi nhận commit; sửa 24 checker, thêm S87, hạ READY 63→58; ghi phát hiện nguồn CTKM, đi tuyến, hợp đồng ETC và giá trị tồn kho.

- Tên commit: fix: doi chieu bo dap an 138 cau voi Bravo that qua UAT truc tiep.
- File triển khai/tài liệu: `.gitignore`, `docs/backlog_tu_phan_hoi_nguoi_dung.md`, `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_month_by_month.md`, `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md`, `docs/huong_dan_ban_giao_uat.md`, `docs/tracking_hoan_thien_du_an_03-30_09_2026.md`, `eslint.config.mjs`, `scripts/kiem_truoc_uat.ps1`, `scripts/verify_etc_channel_scope.py`.
- File kiểm thử thay đổi: `tests/test_sql_doi_chung_138.py`, `tests/test_verify_etc_channel_scope_output.py`.

### 04/09/2026 — 16 commit

Tồn kho hai hệ/năm tài chính; roster đội; mẫu số KPI; V25; CreatedAt; kế hoạch và checker.

#### 27. 10:46:02 — [700ad9f](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/700ad9fdf3c92a5274b41b2af8f914e61150a554)

Sửa bảy ánh xạ câu hỏi–checker, thêm S88–S92 cho hành vi khách hàng, tăng trưởng và thay đổi phân công; đồng bộ tài liệu và SQL test tay.

- Tên commit: fix(checker): sua 7 cau bi gan nham checker, them S88-S92.
- File triển khai/tài liệu: `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_month_by_month.md`, `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md`, `docs/huong_dan_ban_giao_uat.md`, `docs/sql_test_tay_13_cau.sql`, `docs/tracking_hoan_thien_du_an_03-30_09_2026.md`.
- File kiểm thử thay đổi: `tests/test_sql_doi_chung_138.py`.

#### 28. 10:46:42 — [eb8d373](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/eb8d373a99c674ab348c99c786f51fe2a397af58)

Sửa cộng tồn kho qua nhiều năm tài chính, đổi nguồn mẫu số KPI để giữ nhân sự thiếu dòng khách; bổ sung quy tắc diễn giải tăng trưởng/cohort/lịch sử.

- Tên commit: fix(backend): ton kho cong don 3 nam tai chinh, mau so KPI thieu nguoi.
- File triển khai/tài liệu: `backend/local_warehouse.py`, `backend/report_templates.py`, `backend/schema_context.py`, `backend/sync_warehouse.py`.
- File kiểm thử thay đổi: `tests/test_management_rounds_remaining.py`.

#### 29. 14:00:13 — [519db18](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/519db18ce5c1c9fd722b55dbb4e645b15b5cc78e)

Thêm kiểm tra tồn kho sau deploy: cột năm tài chính, dữ liệu đã nạp, số lượng tồn và số lô hết hạn; xuất ĐẠT/CHƯA ĐẠT.

- Tên commit: feat(script): kiem ton kho sau deploy - tu ra ket luan DAT/CHUA DAT.
- File triển khai/tài liệu: `scripts/kiem_ton_kho_sau_deploy.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 30. 14:15:31 — [f5677d9](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/f5677d9252d7af5c47f31f3642198d5b90883e39)

Thêm kiểm thử phân giải DMSId của đội và script chẩn đoán phần doanh thu bị hụt. Chẩn đoán nguyên nhân được cập nhật tiếp ở 77162d9.

- Tên commit: test(qlv): chot phan giai DMSId cua doi + script chan doan.
- File triển khai/tài liệu: `scripts/kiem_phan_giai_doi_qlv.py`.
- File kiểm thử thay đổi: `tests/test_team_dms_resolution.py`.

#### 31. 14:43:01 — [2d38cdc](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/2d38cdc01bf42b8d032d4cb3029f69b85c26b093)

Hoàn thiện định tuyến và mô tả công cụ QLV; siết đường phân giải đội, phạm vi và dữ liệu báo cáo; bổ sung quy tắc 18 về V15/V22/V25.

- Tên commit: fix(qlv): dinh tuyen + mo ta tool cho vai QLV, chot chan hut so lieu.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`, `backend/schema_context.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_daily_kpi_status.py`, `tests/test_employee_kpi.py`, `tests/test_management_rounds_remaining.py`, `tests/test_qlv_unblocked_area_only_tools.py`, `tests/test_revenue_monthly_series.py`, `tests/test_salary_detail.py`.

#### 32. 14:48:08 — [c79517b](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/c79517bcd993e8aeb8acb49d2655a46b7441b1d9)

Bổ sung phép bất biến để bắt các lỗi lớn vừa phát hiện qua đối chiếu ngày 04/09.

- Tên commit: test(bat-bien): canh hai loi nang nhat 04/09 bang phep kiem chay duoc.
- File triển khai/tài liệu: `scripts/doi_chieu_so_lieu_tool_moi.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 33. 15:03:24 — [0a56f3e](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/0a56f3e2a398eac6f3ee07423d054beabf071a3c)

Sửa báo động giả của kiểm_11: lọc theo bản chất dòng dữ liệu thay vì chỉ dựa cờ.

- Tên commit: fix(bat-bien): kiem_11 bao dong gia - loc theo ban chat thay vi theo co.
- File triển khai/tài liệu: `scripts/doi_chieu_so_lieu_tool_moi.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 34. 15:06:48 — [0a45189](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/0a45189a01fcaae723a2fbb76d092955ce69ea77)

Sửa chuỗi ánh xạ checker bị lệch ở nhóm hiệu suất nhân viên.

- Tên commit: fix(checker): sua chuoi anh xa bi lech mot nac o nhom hieu suat nhan vien.
- File triển khai/tài liệu: `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_month_by_month.md`, `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 35. 15:11:07 — [c7c1075](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/c7c1075a0acb3bbda936e41a1fb363cff00af660)

Thêm kiểm_16 để phát hiện đếm trùng số khách hàng.

- Tên commit: test(bat-bien): kiem_16 canh loi dem trung so khach hang.
- File triển khai/tài liệu: `scripts/doi_chieu_so_lieu_tool_moi.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 36. 15:24:43 — [77162d9](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/77162d95ffebc2f9b25a50ee3dfbc8498255404e)

Sửa nguyên nhân đội co lại đầu tháng: hợp roster cuối tháng tròn với snapshot mới nhất, giữ người chưa bán và người mới vào; cập nhật chẩn đoán.

- Tên commit: fix(qlv): danh sach doi co lai theo snapshot giua thang - GOC THAT cua loi M01.
- File triển khai/tài liệu: `backend/report_templates.py`, `scripts/kiem_phan_giai_doi_qlv.py`.
- File kiểm thử thay đổi: `tests/test_team_dms_resolution.py`.

#### 37. 16:05:02 — [74df6b5](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/74df6b588b989e505b9afdd47de25df6dedb8c53)

Đồng bộ hệ kho sản xuất và tách khỏi hệ kho kinh doanh; giữ giới hạn vùng. Theo ghi nhận commit, khắc phục việc chỉ nhìn thấy khoảng 2% giá trị hai hệ kho.

- Tên commit: feat(ton-kho): dong bo he kho SAN XUAT - truoc day chatbot chi thay 2% gia tri.
- File triển khai/tài liệu: `backend/local_warehouse.py`, `backend/report_templates.py`, `backend/schema_context.py`, `backend/sync_warehouse.py`.
- File kiểm thử thay đổi: `tests/test_inventory_two_systems.py`.

#### 38. 16:33:10 — [1e91e37](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/1e91e37078ed53f1b3d0cbaf195457b684af7515)

Gỡ cách diễn giải chênh thời điểm tạo đơn/ngày chứng từ thành nghi vấn chạy KPI hoặc gian lận.

- Tên commit: fix(order-timing): go khung "chay don KPI" - DNH xac nhan do lech vo nghia.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 39. 16:38:16 — [24e8c66](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/24e8c66a643b7f9b28ac119472e257288cc12707)

Soạn bản rút gọn hai câu cần DNH xác nhận: cách đánh giá KPI giữa tháng và vai trò/mã MBKV12.

- Tên commit: docs: ban rut gon 2 cau can DNH xac nhan, han 10/09.
- File triển khai/tài liệu: `docs/DNH_can_xac_nhan_2_cau_han_10-09.md`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 40. 16:46:53 — [b586adc](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/b586adc1558e4e462c3c77e857956546708d2b24)

Gỡ hẳn phép kiểm chênh CreatedAt–DocDate khỏi công cụ bất thường; thống nhất CreatedAt là thời điểm tạo đơn, giữ phần hàng trả/điều chỉnh hợp lệ.

- Tên commit: fix(order-timing): go han phep kiem created_at - hai moc do hai giai doan khac nhau.
- File triển khai/tài liệu: `backend/local_warehouse.py`, `backend/nl2sql.py`, `backend/report_templates.py`, `backend/schema_context.py`, `backend/sync_warehouse.py`, `docs/DNH_can_xac_nhan_2_cau_han_10-09.md`, `docs/chatbot_accuracy_99_backlog_day19-22.md`, `docs/kich_ban_demo1_chatbot.md`.
- File kiểm thử thay đổi: `tests/test_qlv_unblocked_area_only_tools.py`.

#### 41. 16:55:57 — [ea76f53](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/ea76f537971b04f32a97d24cb224eaba601be44a)

Đổi nhãn kho B01 thành trụ sở thuộc hệ kinh doanh, tránh nhầm với hệ kho sản xuất mới đồng bộ.

- Tên commit: fix(ton-kho): doi nhan B01 - trung ten voi he kho san xuat vua dong bo.
- File triển khai/tài liệu: `backend/local_warehouse.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_local_warehouse_migrations.py`.

#### 42. 16:58:15 — [07b2b87](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/07b2b87001ae16ee8bffb58057d7e50d37bb55a6)

Chốt kế hoạch 04–30/09, phân việc theo thư mục, cổng kiểm miễn phí và nguyên tắc kiểm chứng trước UAT.

- Tên commit: docs: ke hoach 04-30/09 sau ngay doi chieu 04/09.
- File triển khai/tài liệu: `docs/ke_hoach_04-30_09_2026.md`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

### 05/09/2026 — 2 commit

Xếp hạng KPI đầu tháng; nhân sự thiếu dữ liệu; khóa kỳ báo cáo.

#### 43. 10:10:56 — [a957a48](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/a957a48b56017903409d34609eca7cf94a5559bf)

Sửa xếp hạng KPI đầu tháng bằng roster kỳ tròn, tránh trả rỗng khi snapshot hiện tại chưa đủ nhân sự.

- Tên commit: fix(kpi): dung roster ky tron cho xep hang dau thang.
- File triển khai/tài liệu: `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_kpi_ranking.py`.

#### 44. 10:18:42 — [c32a405](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/c32a405d60ffa0a18e5f6f4020af62b1c105b542)

Hiển thị rõ nhân sự thiếu dữ liệu và giữ đúng kỳ báo cáo khi đánh giá KPI.

- Tên commit: fix(kpi): hien ro nhan su thieu du lieu va giu dung ky bao cao.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`, `backend/schema_context.py`.
- File kiểm thử thay đổi: `tests/test_employee_kpi.py`, `tests/test_kpi_ranking.py`, `tests/test_management_rounds_remaining.py`.

### 07/09/2026 — 19 commit

Định tuyến C/M/V; đối chiếu doanh thu; target đội; hành vi khách; bán chéo; đơn DMS; đi tuyến.

#### 45. 08:40:24 — [d3626be](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/d3626be9bf6fbdc3c1e4ef8bc7a9a0f7a1a48ea6)

Củng cố câu trả lời biến động khách hàng và chi phí thưởng; cập nhật định tuyến, báo cáo, kiểm thử lương và đọc SQL.

- Tên commit: fix(uat): harden customer movement and bonus cost answers.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_live_sql_reading.py`, `tests/test_management_rounds_remaining.py`, `tests/test_salary_detail.py`.

#### 46. 09:12:17 — [71f585e](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/71f585ec9581184c22b90cd0ff7c36cd98685999)

Chặn kết luận YTD thiếu dữ liệu và làm rõ giới hạn dùng đội hiện tại cho kỳ lịch sử.

- Tên commit: fix(uat): guard incomplete ytd and historical team scope.
- File triển khai/tài liệu: `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_customer_lifecycle.py`, `tests/test_management_periods_inventory.py`.

#### 47. 09:43:31 — [b957283](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/b9572833914284c65ff114fb7d41b8d8127d4e31)

Bổ sung định tuyến và đối chiếu nhóm câu điều hành C-Level; cập nhật xử lý chuỗi kỳ, tồn kho, khách hàng và sản phẩm.

- Tên commit: fix(uat): route and reconcile executive checks.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/query_plan.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_management_periods_inventory.py`, `tests/test_management_rounds_remaining.py`, `tests/test_query_plan.py`, `tests/test_top_products_customers.py`.

#### 48. 09:54:28 — [b9df5b1](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/b9df5b17a30d4a05ec7b27f36e31fb7238ab0549)

Bổ sung định tuyến nhóm câu Giám đốc miền/kênh tới đúng công cụ báo cáo.

- Tên commit: fix(uat): route regional manager questions.
- File triển khai/tài liệu: `backend/nl2sql.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`.

#### 49. 10:05:54 — [be8ca86](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/be8ca866b385360352af8a73c6bf190485d450c6)

Sửa lỗi lint giao diện Next 16 ở panel quản trị, trang chính và hộp thoại.

- Tên commit: fix(frontend): clear Next 16 lint errors.
- File triển khai/tài liệu: `src/app/AdminUsersPanel.tsx`, `src/app/page.tsx`, `src/app/useModal.ts`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 50. 10:34:26 — [d5d0559](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/d5d05596bf90eadee16e3060421455f227b405cd)

Chặn việc gọi chênh doanh thu chưa giải thích được là gap bình thường; yêu cầu có bằng chứng trước kết luận.

- Tên commit: fix(uat): reject unproven revenue gaps.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/query_plan.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_management_rounds_remaining.py`, `tests/test_query_plan.py`.

#### 51. 10:48:05 — [57a245a](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/57a245a87632bf54531a577a7b87a12fc2fdfd32)

Giữ ranh giới phần đã kiểm chứng và chưa kiểm chứng; bổ sung kiểm thử định tuyến và bảo mật.

- Tên commit: fix(uat): preserve partial review boundaries.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/query_plan.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_management_rounds_remaining.py`, `tests/test_query_plan.py`, `tests/test_security_hardening.py`.

#### 52. 11:01:13 — [9398bd1](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/9398bd1e13c55f4d9274d30298c8d1c04783790a)

Củng cố đối chiếu chỉ số đội, xử lý khác biệt phạm vi/nguồn; mở rộng kiểm thử câu quản lý và QLV.

- Tên commit: fix(uat): guard team metric reconciliations.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_management_rounds_remaining.py`, `tests/test_qlv_unblocked_area_only_tools.py`.

#### 53. 11:26:29 — [3ac1135](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/3ac113513ac046e37cd359fd4dcbecd5226373d8)

Khôi phục target đội và điều chỉnh báo cáo ưu tiên theo khoảng hụt chỉ tiêu.

- Tên commit: fix(uat): restore team targets and priority gap focus.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_management_rounds_remaining.py`.

#### 54. 14:26:23 — [4eb8890](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/4eb8890d2fcd71dc5c19e45828066e3743d33fcc)

Đưa CTV vào danh sách đội QLV và thống nhất mốc snapshot của kpi_ranking.

- Tên commit: fix(kpi): include CTV in _team_of_qlv and align fdate in kpi_ranking.
- File triển khai/tài liệu: `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_revenue_tree.py`.

#### 55. 15:18:02 — [616a549](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/616a549078ade16fee9c852194ba14f64458d1b9)

Chuẩn hóa S68 cho V23, thêm chi tiết S18b cho V22 và mở rộng bộ lọc QLV của S69/V21.

- Tên commit: docs: chuan hoa S68 (V23), bo sung S18b chi tiet (V22) va bo loc QLV mo rong cho S69 (V21).
- File triển khai/tài liệu: `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 56. 15:23:18 — [efd02b2](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/efd02b29c0f4cb6aeeda0204e4383b672b6bbd88)

Giữ đúng ngưỡng thưởng riêng của CTV trong cây doanh thu.

- Tên commit: fix(kpi): preserve CTV bonus threshold in revenue tree.
- File triển khai/tài liệu: `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_revenue_tree.py`.

#### 57. 15:40:29 — [6e75e23](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/6e75e23b2fbafc42158661e9b8001bf971a81a43)

Sửa định tuyến và chỉ số đối chiếu cho nhóm câu hành vi khách hàng.

- Tên commit: fix(uat): route and benchmark customer behavior questions.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_management_rounds_remaining.py`.

#### 58. 15:50:04 — [d0393ca](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/d0393ca5d94c9bdef62547395527e1e13e141e97)

Sửa script kiểm phạm vi đơn ETC, bỏ phụ thuộc vào suy luận CreatedAt đã bị loại.

- Tên commit: fix(uat): verify ETC order scope without CreatedAt heuristic.
- File triển khai/tài liệu: `scripts/verify_etc_channel_scope.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 59. 16:02:03 — [fbe55c5](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/fbe55c547356c1cdc7145f6db522497598b53370)

Bổ sung nội dung báo cáo ưu tiên khách hàng và SKU để trả đúng trọng tâm câu hỏi.

- Tên commit: fix(uat): focus customer and SKU priority reports.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_management_rounds_remaining.py`.

#### 60. 16:03:12 — [3e02914](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/3e029141472aa7129ca803db4fb71cfa501fb42f)

Yêu cầu ngưỡng khách hàng lớn trước khi đưa ra hành động giữ chân nhóm khách lớn.

- Tên commit: fix(uat): require large-customer threshold for retention actions.
- File triển khai/tài liệu: `backend/report_templates.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 61. 16:31:18 — [52636dd](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/52636dde3779c56c136f3464d03ab6fccc4b38c8)

Thống nhất chỉ số cơ cấu SKU và số liệu theo cặp sản phẩm trong báo cáo bán chéo.

- Tên commit: fix(uat): align SKU mix and cross-sell pair metrics.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_management_rounds_remaining.py`.

#### 62. 16:38:30 — [e64d9eb](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/e64d9eb977ab3f93dada2450e46870e129c81ede)

Đối chiếu danh sách đơn ngoại lệ với nguồn DMS, bổ sung định tuyến và kiểm thử phạm vi QLV.

- Tên commit: fix(uat): align order exception list with DMS source.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_qlv_unblocked_area_only_tools.py`.

#### 63. 16:52:27 — [faf7f65](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/faf7f653902aeca275eeb859ae10305083a51a87)

Bổ sung báo cáo hiệu quả đi tuyến/viếng thăm từ DMS_DiTuyen và chỉ số liên quan đơn/doanh thu.

- Tên commit: feat(uat): report route visit effectiveness.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`.

### 08/09/2026 — 9 commit

Tồn kho/SKU; giới hạn CTKM/thu tiền; bảo vệ bộ chạy eval; YTD và giới hạn nguồn.

#### 64. 12:49:58 — [c34730c](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/c34730cac8b69c7c9dcbd4a54e95e7440a2da541)

Bổ sung nguy cơ thiếu hàng theo phạm vi kho/vùng, tốc độ bán và khách mua gần đây.

- Tên commit: fix(uat): add scoped inventory supply risk.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_management_periods_inventory.py`.

#### 65. 12:53:45 — [2215bb4](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/2215bb45f7acc3cb376a5da0b88d4aaf5b545b73)

Nêu rõ giới hạn nguồn khuyến mãi, công nợ/thu tiền; cập nhật kiểm thử để tránh suy đoán khi thiếu dữ liệu.

- Tên commit: fix(uat): make source gaps explicit.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_promotion_effectiveness.py`, `tests/test_receivables_overview.py`.

#### 66. 12:55:56 — [c400743](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/c4007436757742e00bccde1b9768d196f98ba57f)

Khóa định tuyến V34 và V37–V39 bằng kiểm thử hồi quy.

- Tên commit: test(uat): lock V34 and V37-V39 routing.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`.

#### 67. 12:59:00 — [f51c039](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/f51c03984eb20f67a3be39b45dfa9d11232a8856)

Ưu tiên nhận diện ý định khuyến mãi trong câu V34.

- Tên commit: fix(uat): prioritize promotion intent for V34.
- File triển khai/tài liệu: `backend/nl2sql.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 68. 13:00:00 — [07c7438](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/07c7438b006b1c39f0fced812b6a7c0b548a6567)

Ẩn API key trong bộ chạy 138 câu để tránh ghi lộ khóa khi vận hành.

- Tên commit: fix(eval): redact API key from 138-case runner.
- File triển khai/tài liệu: `scripts/run_bo_138_cau.py`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 69. 13:19:37 — [1081be4](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/1081be4bbc048b36a85be002a1a2857073136b91)

Cho cổng kiểm dữ liệu nhận diện giới hạn nguồn đã được ghi nhận, tách khỏi lỗi code/đối chiếu.

- Tên commit: fix(uat): allow documented source gaps in gate.
- File triển khai/tài liệu: `scripts/doi_chieu_so_lieu_tool_moi.py`.
- File kiểm thử thay đổi: `tests/test_doi_chieu_40_tools.py`.

#### 70. 13:24:17 — [3da7744](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/3da7744f2dae5f0056cee248121992ff2b31c2cd)

Dừng vòng chạy 138 câu khi nhà cung cấp báo lỗi tài khoản; bổ sung kiểm thử để tránh tiếp tục gọi hàng loạt.

- Tên commit: fix(eval): stop 138 run on provider account errors.
- File triển khai/tài liệu: `scripts/run_bo_138_cau.py`.
- File kiểm thử thay đổi: `tests/test_run_bo_138_cau.py`.

#### 71. 23:20:10 — [ac4cdab](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/ac4cdab6391c01867584116defd6bb89ab4a86ba)

Chặn phép tính YTD/kế hoạch năm không đủ dữ liệu trong bước kiểm câu trả lời.

- Tên commit: fix(uat): block incomplete YTD calculations.
- File triển khai/tài liệu: `backend/query_plan.py`.
- File kiểm thử thay đổi: `tests/test_query_plan.py`.

#### 72. 23:23:59 — [c28f2ba](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/c28f2babd9db49599c2ed6b0d2b4830dda821dc0)

Đưa giới hạn nguồn nằm sâu trong kết quả công cụ lên phần chưa kiểm chứng của câu trả lời.

- Tên commit: fix(uat): surface nested source limitations.
- File triển khai/tài liệu: `backend/query_plan.py`.
- File kiểm thử thay đổi: `tests/test_query_plan.py`.

### 09/09/2026 — 14 commit

Vá smoke C31/M20/V33; V38/V39; C20/C28/C29/C54; giao việc và kiểm tra Antigravity.

#### 73. 00:46:18 — [d28531c](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/d28531ce1765d1c559c4aa52857395da4ed529bb)

Vá các lỗi smoke C31/M20/V33: phân rã tăng trưởng khách hàng, ranh giới đối chiếu thưởng/KPI và tra đơn theo kỳ; cập nhật cây doanh thu.

- Tên commit: fix(uat): close C31 M20 V33 smoke gaps.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/query_plan.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_qlv_unblocked_area_only_tools.py`, `tests/test_query_plan.py`, `tests/test_revenue_tree.py`.

#### 74. 08:22:47 — [644fef1](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/644fef1d1b0e1b52fe943065c9870ac3edbc0cc6)

Làm rõ số lượng và phần giao nhau của nhóm đơn hủy/chưa hóa đơn/chênh ngày, tránh cộng trùng ngoại lệ V33.

- Tên commit: fix(uat): make V33 exception counts reliable.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_qlv_unblocked_area_only_tools.py`, `tests/test_query_plan.py`.

#### 75. 09:02:11 — [f512987](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/f5129872481081189204539ab06aba74c8609039)

Ưu tiên đúng nhóm tồn thiếu hoặc tồn cao cho V38/V39; giữ thông tin SKU/khách liên quan và giới hạn suy luận.

- Tên commit: fix(uat): focus inventory evidence for V38 V39.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/query_plan.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_management_periods_inventory.py`, `tests/test_query_plan.py`.

#### 76. 09:25:02 — [8281fa1](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/8281fa16b80b6a67f7da66846053690f1915b093)

Chặn kết luận KPI giữa tháng thiếu căn cứ khi chỉ có doanh số MTD và target cả tháng.

- Tên commit: fix(uat): avoid unsupported midmonth KPI conclusions.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/query_plan.py`.
- File kiểm thử thay đổi: `tests/test_query_plan.py`.

#### 77. 09:26:36 — [5404c3a](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/5404c3adf7418f5a27e5ceb96075f4db6b3d6fe7)

Ẩn tên công cụ nội bộ trong câu trả lời UAT để dễ đọc hơn.

- Tên commit: fix(ui): hide internal tool names in UAT answers.
- File triển khai/tài liệu: `backend/query_plan.py`.
- File kiểm thử thay đổi: `tests/test_query_plan.py`.

#### 78. 09:59:06 — [98abacb](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/98abacbc839528cabcc06852cbc2e8e7e2079309)

Sửa đối chiếu C20 và phạm vi ảnh hưởng thay đổi phân công của C28; bổ sung kiểm thử báo cáo và định tuyến.

- Tên commit: fix(uat): reconcile C20 and scope C28 assignment changes.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/query_plan.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_management_rounds_remaining.py`, `tests/test_query_plan.py`.

#### 79. 11:37:35 — [fbcf9f5](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/fbcf9f557abe85c42d96857b6eccc4f572ad262b)

Bổ sung chuỗi vòng đời khách hàng C29 từ hóa đơn, kết hợp với cờ NC/RO có trong snapshot.

- Tên commit: feat(uat): add C29 invoice customer lifecycle series.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/query_plan.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_business_composite_tools.py`, `tests/test_customer_lifecycle.py`, `tests/test_query_plan.py`.

#### 80. 13:56:08 — [94d444a](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/94d444a60ea734f3827d2e69e2acaa1e9b5de4ec)

Cố định C29 về phạm vi OTC đã đối chiếu, tránh trộn số khách của hai kênh hoặc hai nguồn không cùng phạm vi.

- Tên commit: fix(uat): lock C29 to reconciled OTC lifecycle.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/query_plan.py`.
- File kiểm thử thay đổi: `tests/test_query_plan.py`.

#### 81. 14:03:30 — [78e8030](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/78e8030eddbe01c57d53fd1752090feaf7fd5390)

Ổn định cửa sổ lịch sử C29 để số tái kích hoạt không đổi chỉ vì mở rộng số tháng hiển thị.

- Tên commit: fix(uat): stabilize C29 lifecycle history window.
- File triển khai/tài liệu: `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_customer_lifecycle.py`.

#### 82. 14:42:12 — [28719bb](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/28719bbdf51a159f8046ab8a34e56f3d72c3e879)

Sửa C54 dùng roster đầy đủ khi kiểm chất lượng dữ liệu, phân biệt nhân viên và tầng quản lý.

- Tên commit: fix(uat): align C54 data quality with full roster.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_management_rounds_remaining.py`.

#### 83. 14:49:04 — [8202085](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/82020853103aed472a6e730de3394279374de2f6)

Chặn kết luận chưa có căn cứ về trạng thái chốt snapshot trong C54.

- Tên commit: fix(uat): prevent unsupported C54 snapshot conclusions.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_management_rounds_remaining.py`.

#### 84. 14:56:29 — [29da152](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/29da152b1b76f7a6b58891d4e0b7954aa349c0e3)

Sửa C54 kiểm chất lượng ngày tại mốc lịch sử, tránh diễn giải sai chứng từ tương lai.

- Tên commit: fix(uat): correct C54 historical date quality checks.
- File triển khai/tài liệu: `backend/nl2sql.py`, `backend/report_templates.py`.
- File kiểm thử thay đổi: `tests/test_management_rounds_remaining.py`.

#### 85. 16:47:08 — [dc90454](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/dc904546efd04403d91f65c13dee07ef5ef03408)

Tạo handoff chi tiết cho Antigravity: cụm lỗi, file/hàm cần sửa, test, tài khoản và điều kiện retest.

- Tên commit: docs: add UAT repair handoff for Antigravity.
- File triển khai/tài liệu: `docs/handoff_antigravity_uat_09-09.md`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

#### 86. 20:13:12 — [9c370e8](https://github.com/DNH-x-MCNA/DNH-x-MCNA/commit/9c370e8b4c22b18f6feed0724eb4b6c88d4bbccf)

Chốt báo cáo kiểm tra Antigravity; ghi nhận checker sửa dở, M16 mới có bản thử local và các phần chưa hoàn tất.

- Tên commit: docs: record UAT progress and Antigravity audit.
- File triển khai/tài liệu: `docs/bao_cao_tien_do_09-09_chot_phien.md`.
- File kiểm thử thay đổi: không có file trong tests/ ở commit này.

## 7. Tra cứu tiếp

- [Handoff sửa UAT cho Antigravity](handoff_antigravity_uat_09-09.md).
- [Báo cáo kiểm tra và chốt phiên 09/09](bao_cao_tien_do_09-09_chot_phien.md).
- [Kế hoạch 04–30/09](ke_hoach_04-30_09_2026.md).
- [Bộ câu hỏi và SQL đối chứng](bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md).

Các báo cáo số liệu/chi phí/triển khai chính thức cần đính kèm log hoặc kết quả retest tương ứng. Báo cáo này cung cấp vết công việc theo commit và trạng thái tồn đọng tại mốc chốt.
