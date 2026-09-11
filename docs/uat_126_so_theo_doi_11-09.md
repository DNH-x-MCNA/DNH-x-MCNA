# Sổ theo dõi 126 câu UAT — mốc 11/09/2026 sáng

Nguồn: đọc tab kết quả trên sheet UAT lúc ~09:30 ngày 11/09, theo **tên cột** (sheet đã thêm cột `TÍnh cần thiết của câu hỏi`). Checker lấy từ `docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md` tại `ab2c04a`. Tài liệu này **không thay** sheet: chỉ là bản đối chiếu để người chấm biết dòng nào phải xem lại.

## Tổng hợp theo rubric của kế hoạch 11–20/09

| Trạng thái | Số câu | Nghĩa |
|---|---:|---|
| ĐẠT | 63 | Chốt đạt hoặc ghi khớp không điều kiện, và lần chấm diễn ra sau bản sửa gần nhất |
| CHỜ CHỐT GIỚI HẠN | 4 | Khớp phần chính nhưng có giới hạn nguồn — người chấm duyệt nhãn "ĐẠT — giới hạn nguồn" hay không |
| CẦN XÁC NHẬN | 2 | Test và sửa cùng ngày — không biết lần chấm trước hay sau bản sửa |
| CHỜ KIỂM | 28 | Có bản sửa sau lần chấm, hoặc đối chiếu lúc đó không đúng phạm vi — không cộng vào đạt |
| CHƯA ĐẠT | 29 | Đã test, không khớp, chưa có bản sửa |
| CHƯA TEST | 0 | Chưa có kết quả chạy |
| **Tổng** | **126** | |

- Đạt chắc chắn: **63/126 = 50.0%**. Nếu các dòng chờ chốt giới hạn và cần xác nhận đều được duyệt: 69/126 = 54.8%.
- Kế hoạch ghi 72/126. Chín câu kế hoạch tính đạt nhưng sổ này chưa tính: **C42, M27** (ghi khớp trước ngày có bản sửa), **V17** (lúc chấm S38 chưa lọc được theo đội), **C39** (đối chiếu với S26 bản so kỳ chưa tròn), **C47, M05** (checker S64/S58 đếm tháng rải rác thành chuỗi liên tiếp), **V22** (test và sửa cùng ngày), **C11, M41** (khớp phần chính, còn giới hạn nguồn chờ duyệt).
- Ghi chú "chưa kiểm tra lại" trong cột Đã sửa chỉ có nghĩa khi ngày test **trước** ngày sửa. C48, M01, M03, M11 có ngày test sau ngày sửa nên kết quả hợp lệ — chỉ là ghi chú chưa được cập nhật.
- Chờ chốt giới hạn: C11, C41, M41, V05. Cần xác nhận: V11, V22.
- Phân công người chấm: A = 63 câu, B = 63 câu.

## Dòng cần xác nhận trước khi chạy vòng nền

| Mã | Trạng thái | Việc cần làm |
|---|---|---|
| C11 | CHỜ CHỐT GIỚI HẠN | Khớp sau bản sửa 07/09; giới hạn: top SKU năm 2025 vượt 12 tháng chi tiết — người chấm duyệt giới hạn |
| C16 | ĐẠT | S11 cũ đếm tháng giảm giá rải rác thành chuỗi — chấm lại |
| C24 | ĐẠT | Đã phân xử: chatbot đúng, S51 lệch 1–2 khách — S51 cần sửa cho vòng sau |
| C39 | CHỜ KIỂM | S26 bản 10/09 so 4 ngày T9 với cả T8 (2.575 khách/36,5 tỷ); đúng là T8 so T7 đủ tháng: 1.647 khách/20,3 tỷ (nợ snapshot 04/09) — chấm lại trên kho máy 24 |
| C41 | CHỜ CHỐT GIỚI HẠN | Xác nhận với người chấm |
| C42 | CHỜ KIỂM | Chatbot có SKU mà query không có — soát S47b bỏ sót trước khi coi là lỗi chatbot |
| C46 | ĐẠT | Đối chiếu với S32 trước khi thêm TK (+5,11 tỷ MN) — retest |
| C47 | CHỜ KIỂM | S64 cũ đếm tháng dưới 80% rải rác thành chuỗi: 80 người "từ 6 tháng liên tiếp", đúng là 21. Kèm thêm TK từ 10/09 — chấm lại |
| M05 | CHỜ KIỂM | S58 cũ đếm tháng rải rác: có vùng "7 tháng liên tiếp"; đúng là MB/MN/MT mỗi vùng tối đa 3 tháng (MB 05→07/2026, hụt 31,5 tỷ) — chấm lại |
| M13 | ĐẠT | Checker vừa thêm TK — chỉ retest nếu lúc chấm không theo phạm vi MB |
| M14 | ĐẠT | Checker vừa thêm TK — chỉ retest nếu lúc chấm không theo phạm vi MB |
| M15 | ĐẠT | Checker vừa thêm TK — chỉ retest nếu lúc chấm không theo phạm vi MB |
| M16 | CHƯA ĐẠT | S55 cũ đếm tháng giảm rải rác (60 dòng 6–8 tháng). Đúng: MB hiện 1 người giảm ≥3 tháng liên tiếp (Phạm Xuân Toàn HPO1, 05→08/2026), 3 người ≥2. Nhận xét "chatbot chỉ nêu 1 người" dựa trên checker lỗi — chấm lại |
| M17 | ĐẠT | Checker vừa thêm TK — chỉ retest nếu lúc chấm không theo phạm vi MB |
| M19 | ĐẠT | Checker vừa thêm TK — chỉ retest nếu lúc chấm không theo phạm vi MB |
| M28 | CHƯA ĐẠT | Checker S38 sai chủ đề (nhân viên–target); đúng chủ đề là S75 gộp tỷ lệ theo tháng |
| M38 | CHƯA ĐẠT | Cùng S26 — dùng bản tháng tròn 11/09 |
| M41 | CHỜ CHỐT GIỚI HẠN | Khớp doanh thu ETC. Phần "thu tiền từng tháng" không có nguồn (S45 BLOCKED_HISTORY) — chỉ đạt nếu chatbot nói rõ giới hạn; ô Chatbot response đang trống |
| V05 | CHỜ CHỐT GIỚI HẠN | Xác nhận với người chấm |
| V11 | CẦN XÁC NHẬN | Xác nhận với người chấm |
| V13 | ĐẠT | Cùng S55 — chấm lại với checker đã sửa, lọc đúng đội |
| V17 | CHỜ KIỂM | Chốt đạt trước khi S38 có lọc đội (10/09) — chấm lại với @ManagerCode đúng đội |
| V22 | CẦN XÁC NHẬN | Test và sửa cùng ngày 07/09 — xác nhận lần chấm là sau bản sửa |
| V36 | CHƯA ĐẠT | Cùng S26 — dùng bản tháng tròn 11/09, lọc đúng đội |

## Đủ 126 câu

| Mã | Vai | Chấm | Cụm | Checker | Trạng thái | Kết quả chạy (rút gọn) |
|---|---|---|---|---|---|---|
| C01 | C-Level | A | — | S01 | ĐẠT | Khớp dữ liệu |
| C02 | C-Level | A | A | S02 | CHỜ KIỂM | % đạt target của miền nam bị lệch, MB và MT đều đúng |
| C03 | C-Level | A | A | S79 | CHỜ KIỂM | Không khớp dữ liệu, cần xem lại cả chatbot và query SQL |
| C05 | C-Level | A | — | S04 | ĐẠT | Khớp dữ liệu |
| C06 | C-Level | A | — | S05 | ĐẠT | Khớp dữ liệu |
| C07 | C-Level | A | — | S06 | ĐẠT | Khớp dữ liệu |
| C08 | C-Level | A | A | S80 | CHỜ KIỂM | SQL trả về không đúng trọng tâm |
| C09 | C-Level | A | — | S07 | ĐẠT | Khớp dữ liệu |
| C10 | C-Level | A | — | S08 | ĐẠT | Khớp dữ liệu |
| C11 | C-Level | A | — | S70 | CHỜ CHỐT GIỚI HẠN | Khớp dữ liệu, tuy nhiên chatbot không thể tính top 10 sp năm 2025 do g |
| C12 | C-Level | A | — | S09 | ĐẠT | Khớp dữ liệu |
| C13 | C-Level | A | E | S87 | CHỜ KIỂM | SQL trả về không đúng trọng tâm |
| C16 | C-Level | A | — | S11 | ĐẠT | Khớp dữ liệu |
| C17 | C-Level | A | — | S77 | ĐẠT | Khớp dữ liệu |
| C18 | C-Level | A | — | S12 | ĐẠT | Khớp dữ liệu |
| C20 | C-Level | A | C | S13 | CHỜ KIỂM | Không khớp dữ liệu, đã sửa SQL theo 2 tháng 7 và 9 |
| C21 | C-Level | A | — | S14 | ĐẠT | Khớp dữ liệu |
| C22 | C-Level | A | — | S49 | ĐẠT | Khớp dữ liệu |
| C23 | C-Level | A | — | S50 | ĐẠT | Khớp dữ liệu |
| C24 | C-Level | A | — | S51 | ĐẠT | Một số tỉnh/thành phố như Hà Nội, TpHCM, vv bị lệch 1-2 khách so với q |
| C26 | C-Level | A | — | S16 | ĐẠT | Khớp dữ liệu |
| C27 | C-Level | A | — | S17 | ĐẠT | Khớp dữ liệu |
| C28 | C-Level | A | C | S91 | CHỜ KIỂM | Không khớp dữ liệu, đã sửa lại query câu lệnh 3 cần kiểm chứng |
| C29 | C-Level | A | — | S18 | ĐẠT | Không khớp dữ liệu |
| C30 | C-Level | A | C | S19 | CHƯA ĐẠT | Không khớp dữ liệu, đã sửa query cần xem lại |
| C31 | C-Level | A | — | S90 | ĐẠT | Không khớp dữ liệu, đã sửa query cần xem lại |
| C32 | C-Level | A | — | S71 | ĐẠT | Khớp dữ liệu |
| C33 | C-Level | A | — | S21 | ĐẠT | Khớp dữ liệu |
| C34 | C-Level | A | D | S22 | CHƯA ĐẠT | Không khớp dữ liệu, một số sản phẩm lệch tháng phát hành |
| C35 | C-Level | A | — | S23 | ĐẠT | Khớp dữ liệu |
| C36 | C-Level | A | — | S73 | ĐẠT | Khớp dữ liệu |
| C37 | C-Level | A | G | S25 | CHƯA ĐẠT | sai checker do check local |
| C38 | C-Level | A | G | S45 | CHƯA ĐẠT | SQL trả về không đúng trọng tâm |
| C39 | C-Level | A | — | S26 | CHỜ KIỂM | sai checker do check local |
| C40 | C-Level | A | G | S24 | CHƯA ĐẠT | sai checker do check local |
| C41 | C-Level | A | F | S27 | CHỜ CHỐT GIỚI HẠN | Khớp số lượng bán bình quân/tháng nhưng lệch số hàng tồn và số tháng t |
| C42 | C-Level | A | — | S47 | CHỜ KIỂM | Khớp dữ liệu nhưng trong query không có SKU mã 71190230050 mà chat lại |
| C43 | C-Level | A | H | S29 | CHƯA ĐẠT | Chatbot vẫn phản hồi nhưng không đưa ra câu trả lời do không có dữ liệ |
| C44 | C-Level | A | H | S86 | CHƯA ĐẠT | SQL trả về không đúng trọng tâm |
| C45 | C-Level | A | — | S30 | ĐẠT | Lệch số người có target hợp lệ |
| C46 | C-Level | A | — | S32 | ĐẠT | Khớp dữ liệu |
| C47 | C-Level | A | — | S64 | CHỜ KIỂM | Khớp dữ liệu |
| C48 | C-Level | A | — | S33 | ĐẠT | Khớp dữ liệu |
| C52 | C-Level | A | I | S36 | CHƯA ĐẠT | SQL trả về không đúng trọng tâm, chatbot vẫn phản hồi nhưng không trả  |
| C53 | C-Level | A | — | S37 | ĐẠT | Khớp dữ liệu |
| C54 | C-Level | A | B | S38 | CHỜ KIỂM | Không khớp dữ liệu, cần xem lại cả chatbot và query SQL |
| M01 | GĐ miền/kênh | A | — | S01 | ĐẠT | Khớp dữ liệu |
| M02 | GĐ miền/kênh | A | A | S43 | CHƯA ĐẠT | Chưa thể kiểm chúng do tháng 9 chưa nhập target |
| M03 | GĐ miền/kênh | A | — | S04 | ĐẠT | Khớp dữ liệu |
| M04 | GĐ miền/kênh | A | — | S14 | ĐẠT | Khớp dữ liệu |
| M05 | GĐ miền/kênh | A | — | S58 | CHỜ KIỂM | Khớp dữ liệu |
| M06 | GĐ miền/kênh | A | — | S03 | ĐẠT | Khớp dữ liệu |
| M07 | GĐ miền/kênh | A | — | S07 | ĐẠT | Khớp dữ liệu |
| M08 | GĐ miền/kênh | A | — | S90 | ĐẠT | Không khớp dữ liệu về số khách, cần kiểm tra lại query |
| M09 | GĐ miền/kênh | A | — | S09 | ĐẠT | Khớp dữ liệu |
| M10 | GĐ miền/kênh | A | — | S52 | ĐẠT | Khớp dữ liệu |
| M11 | GĐ miền/kênh | A | — | S39 | ĐẠT | Khớp dữ liệu |
| M12 | GĐ miền/kênh | A | — | S31 | ĐẠT | Khớp dữ liệu |
| M13 | GĐ miền/kênh | A | — | S65 | ĐẠT | Khớp dữ liệu |
| M14 | GĐ miền/kênh | A | — | S54 | ĐẠT | Khớp dữ liệu |
| M15 | GĐ miền/kênh | A | — | S32 | ĐẠT | Khớp dữ liệu |
| M16 | GĐ miền/kênh | A | B | S55 | CHƯA ĐẠT | Chatbot cần trả lời rõ ràng hơn, hiện chỉ nêu 1 nhân viên trong khi qu |
| M17 | GĐ miền/kênh | A | — | S85 | ĐẠT | Khớp dữ liệu |
| M18 | GĐ miền/kênh | B | — | S81 | ĐẠT | Khớp dữ liệu |
| M19 | GĐ miền/kênh | B | — | S66 | ĐẠT | Khớp dữ liệu |
| M20 | GĐ miền/kênh | B | B | S33 | CHƯA ĐẠT | TP không có quyền xem lương thưởng chi tiết, cần xác nhận |
| M21 | GĐ miền/kênh | B | — | S20 | ĐẠT | Khớp dữ liệu |
| M22 | GĐ miền/kênh | B | C | S88 | CHƯA ĐẠT | Không khớp dữ liệu, cần xem lại query |
| M23 | GĐ miền/kênh | B | C | S67 | CHƯA ĐẠT | Tổng khách tháng 8 lệch 1 khách |
| M24 | GĐ miền/kênh | B | C | S92 | CHƯA ĐẠT | KKhông khớp dữ liệu, cần check query |
| M25 | GĐ miền/kênh | B | D | S89 | CHƯA ĐẠT | Không khớp sô liệu, cần kiểm tra query |
| M26 | GĐ miền/kênh | B | — | S89 | ĐẠT | Khớp dữ liệu |
| M27 | GĐ miền/kênh | B | — | S53 | CHỜ KIỂM | Khớp dữ liệu |
| M28 | GĐ miền/kênh | B | B | S75 | CHƯA ĐẠT | Không khớp dữ liệu, cần kiểm tra query |
| M29 | GĐ miền/kênh | B | — | S15 | ĐẠT | Khớp dữ liệu |
| M30 | GĐ miền/kênh | B | — | S48 | ĐẠT | Khớp dữ liệu |
| M31 | GĐ miền/kênh | B | — | S21 | ĐẠT | Khớp dữ liệu |
| M32 | GĐ miền/kênh | B | D | S46 | CHƯA ĐẠT | Hệ thống không có khái niệm/nhãn "SKU chiến lược" trong danh mục sản p |
| M33 | GĐ miền/kênh | B | D | S72 | CHƯA ĐẠT | Không khớp dữ liệu, SKU chat trả về không có trong query |
| M34 | GĐ miền/kênh | B | — | S22 | ĐẠT | Khớp dữ liệu |
| M35 | GĐ miền/kênh | B | E | S12 | CHƯA ĐẠT | Không khớp dữ liệu, 1 chương trình có nhiều tháng triển khai, chatbot  |
| M36 | GĐ miền/kênh | B | E | S78 | CHƯA ĐẠT | Không có công cụ nào tính được tỷ lệ chiết khấu/doanh thu theo vùng ha |
| M37 | GĐ miền/kênh | B | G | S25 | CHƯA ĐẠT | Bảng fact_congno_khachhang là bảng local, không test |
| M38 | GĐ miền/kênh | B | G | S26 | CHƯA ĐẠT | Bảng fact_congno_khachhang là bảng local, không test |
| M40 | GĐ miền/kênh | B | F | S28 | CHỜ KIỂM | Không khớp dữ liệu, cần kiểm tra SQL |
| M41 | GĐ miền/kênh | B | — | S29 | CHỜ CHỐT GIỚI HẠN | Khớp dữ liệu doanh thu ETC nhưng không thể kiểm tra dư nợ do bảng fact |
| M42 | GĐ miền/kênh | B | H | S86 | CHƯA ĐẠT | Chưa có khóa liên kết chính thức giữa hóa đơn và hợp đồng/gói thầu ETC |
| M44 | GĐ miền/kênh | B | I | S36 | CHƯA ĐẠT | SQL trả về không đúng trọng tâm |
| V01 | QLV | B | — | S43 | ĐẠT | Khớp dữ liệu |
| V02 | QLV | B | — | S59 | ĐẠT | Khớp dữ liệu |
| V03 | QLV | B | A | S59 | CHƯA ĐẠT | Chưa nhập target tháng 9, chưa thể kiểm chứng |
| V04 | QLV | B | — | S57 | ĐẠT | Khớp dữ liệu |
| V05 | QLV | B | A | S09 | CHỜ CHỐT GIỚI HẠN | Khớp tổng số đơn và doanh thu gốc nhưng chưa thể kiểm chứng số đơn bất |
| V06 | QLV | B | — | S07 | ĐẠT | Khớp dữ liệu |
| V07 | QLV | B | — | S05 | ĐẠT | Khớp dữ liệu |
| V08 | QLV | B | — | S60 | ĐẠT | Khớp dữ liệu |
| V10 | QLV | B | A | S84 | CHỜ KIỂM | SQL trả về không đúng trọng tâm |
| V11 | QLV | B | A | S56 | CẦN XÁC NHẬN | Khớp doanh số các TDV nhưng một số lại bị thiếu mất target tháng 7 tro |
| V12 | QLV | B | — | S31 | ĐẠT | Khớp dữ liệu |
| V13 | QLV | B | — | S55 | ĐẠT | Khớp dữ liệu |
| V14 | QLV | B | — | S44 | ĐẠT | Khớp dữ liệu |
| V15 | QLV | B | C | S61 | CHỜ KIỂM | SQL trả về không đúng trọng tâm |
| V17 | QLV | B | — | S38 | CHỜ KIỂM | SQL không phù hợp, trả về toàn công ty thay vì chỉ đội MBKV2 |
| V18 | QLV | B | B | S33 | CHỜ KIỂM | SQL không phù hợp, trả về toàn công ty thay vì chỉ đội MBKV2 |
| V19 | QLV | B | — | S20 | ĐẠT | Khớp dữ liệu |
| V20 | QLV | B | — | S40 | ĐẠT | Khớp dữ liệu |
| V21 | QLV | B | C | S69 | CHƯA ĐẠT | SQL trả về thiếu thông tin 2 khách mã MBI ở trên, các khách còn lại đã |
| V22 | QLV | B | — | S18 | CẦN XÁC NHẬN | Khớp dữ liệu |
| V23 | QLV | B | C | S68 | CHỜ KIỂM | SQL trả về không đúng trọng tâm |
| V24 | QLV | B | C | S62 | CHỜ KIỂM | SQL trả về không đúng trọng tâm |
| V25 | QLV | B | D | S41 | CHỜ KIỂM | SQL trả về thiếu thông tin 2 bên, khó để kiểm chứng |
| V26 | QLV | B | C | S63 | CHỜ KIỂM | SQL trả về không đúng trọng tâm |
| V27 | QLV | B | — | S75 | ĐẠT | Khớp dữ liệu, không có khách chưa gán tdv |
| V28 | QLV | B | C | S83 | CHỜ KIỂM | SQL trả về không đúng trọng tâm |
| V29 | QLV | B | D | S21 | CHỜ KIỂM | SQL trả về không đúng trọng tâm |
| V30 | QLV | B | D | S46 | CHỜ KIỂM | Chatbot trả lời không có target theo từng SKU |
| V31 | QLV | B | D | S23 | CHỜ KIỂM | SQL trả về không đúng trọng tâm |
| V32 | QLV | B | D | S74 | CHỜ KIỂM | dữ liệu theo cặp không khớp |
| V33 | QLV | B | — | S42 | ĐẠT | SQL trả về không có các đơn trong chatbot |
| V34 | QLV | B | E | S12 | CHỜ KIỂM | Chat không trả về thông tin về các mục khuyến mãi |
| V35 | QLV | B | G | S25 | CHƯA ĐẠT | Bảng fact_congno_khachhang là bảng local, không test |
| V36 | QLV | B | G | S26 | CHƯA ĐẠT | Bảng fact_congno_khachhang là bảng local, không test |
| V37 | QLV | B | G | S45 | CHỜ KIỂM | Chat trả lời không có dữ liệu để trả lời, cần confirm |
| V38 | QLV | B | — | S47 | ĐẠT | Không có dữ liệu về SKU khách cần, cần confirm |
| V39 | QLV | B | — | S28 | ĐẠT | SQL trả về không đúng trọng tâm |
| V40 | QLV | B | B | S76 | CHƯA ĐẠT | Chưa có target tháng 9, chưa thể kiểm chứng |

## Ngoài phạm vi (12 câu, giữ lịch sử, không tính vào tử/mẫu)

- C04 — LOẠI — NGOÀI PHẠM VI
- C14 — LOẠI — NGOÀI PHẠM VI
- C15 — LOẠI — NGOÀI PHẠM VI
- C19 — LOẠI — NGOÀI PHẠM VI
- C25 — TẠM LOẠI — THIẾU NGUỒN
- C49 — TẠM LOẠI — THIẾU NGUỒN
- C50 — LOẠI — NGOÀI PHẠM VI
- C51 — LOẠI — NGOÀI PHẠM VI
- M39 — LOẠI — NGOÀI PHẠM VI
- M43 — LOẠI — NGOÀI PHẠM VI
- V09 — LOẠI — NGOÀI PHẠM VI
- V16 — TẠM LOẠI — THIẾU NGUỒN
