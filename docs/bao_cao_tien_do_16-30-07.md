# BÁO CÁO TIẾN ĐỘ — Dự án Dược Nam Hà (DNH)
### Kỳ báo cáo: 16/07 → 30/07/2026 (2 tuần, kể từ buổi họp 16/07) · Đơn vị thực hiện: MCNA
*(Số liệu chốt đến 28/07 — chạy lại sáng 30/07 để lấy số của ngày báo cáo)*

---

## Tóm tắt cho Ban điều hành

| | |
|---|---|
| **Trọng tâm 2 tuần qua** | Kiểm định độ chính xác số liệu, rồi bịt các lỗ hổng còn sót |
| **Kết quả kiểm định** | ✅ **15/15 hạng mục đạt** — lệch 0 đồng với hệ thống nguồn của DNH |
| **Lỗi số liệu đã tìm & sửa** | **9 lỗi**, trong đó 4 lỗi ảnh hưởng trực tiếp tới đánh giá/lương nhân viên |
| **Lỗ hổng phân quyền đã bịt** | **3 lỗ hổng** — tất cả do MCNA tự rà soát phát hiện, không phải khách báo |
| **Demo #1 Chatbot** | 🟡 Đúng tiến độ — kịch bản + đáp án đối chiếu đã sẵn sàng, đang kiểm chứng từng câu. Hạn **09/08** |
| **Cần DNH quyết** | **4 điểm**, trong đó 1 điểm đang chặn Demo #1 (xem Trang 4) |

---

# TRANG 1/4 — Việc đã làm (Người thực hiện: Lê Việt Đặng)

### A. Kiểm định độ chính xác dữ liệu theo 4 lớp ⭐

Kiểm từ dưới lên — cá nhân → quản lý → vùng → toàn công ty, đối chiếu với hệ thống nguồn của DNH:

| Lớp | Phạm vi kiểm | Kết quả |
|---|---|---|
| Cá nhân | Doanh số từng nhân viên bán hàng | ✅ Đúng |
| Quản lý | Tổng đội từng quản lý vùng | ✅ Khớp tuyệt đối |
| Vùng | Doanh thu & công nợ theo miền | ✅ Lệch 0 đồng |
| Toàn công ty | Doanh thu, công nợ, KPI, tồn kho | ✅ Khớp hóa đơn gốc |

**→ 15/15 hạng mục đạt.** Phương pháp kiểm theo lớp này là thứ giúp tìm ra phần lớn lỗi bên dưới.

### B. Lỗi số liệu đã phát hiện và sửa (9 lỗi)

**Nhóm ảnh hưởng tới đánh giá & lương nhân viên:**

1. **Doanh số bị tính gấp đôi trong KPI** — chỉ tiêu của nhân viên và của quản lý là hai cách nhìn
   *cùng* một khoản doanh thu, từng bị cộng gộp. Phát hiện qua tổng KPI (4,45 tỷ) cao hơn cả doanh thu
   hóa đơn thật (3,32 tỷ) — bất khả thi. Sửa còn 2,27 tỷ.
2. **Chỉ tiêu tháng bị lấy nhầm của tháng khác** *(mới, tuần này)* — khi xem doanh số theo ngày của
   một nhân viên, hệ thống lấy chỉ tiêu **cao nhất trong 3 tháng gần nhất** thay vì của đúng tháng
   đang xem. Trên một nhân viên thật: lấy 343,7 triệu (của tháng 4) thay vì 302,2 triệu thực tế.

   | | Trước khi sửa | Sau khi sửa |
   |---|---|---|
   | Mức hoàn thành tháng | 65,2% | **74,1%** |
   | Số ngày bị chấm Đỏ | 11 | **10** |

   Nhân viên bị báo thấp hơn thực tế **9 điểm phần trăm**, 3 ngày bị chấm màu xấu oan. Lỗi áp dụng cho
   **mọi nhân viên bán hàng**.
3. **Hai nhân viên biến mất khỏi mọi báo cáo** — dữ liệu gốc đánh dấu nhầm là "trùng lặp". Đáng lo hơn
   báo cáo: cờ này còn tác động vào **chính thủ tục tính lương** của DNH, nên có khả năng 2 người đang
   bị tính thiếu thưởng thật (xem Trang 4, mục 3).
4. **"Đạt chỉ tiêu" đếm gộp cả nhân viên lẫn quản lý** — hai tầng khác nhau, đếm chung ra số sai.

**Nhóm số liệu tổng hợp:**

5. **Công nợ báo sai lệch lớn** — công thức cũ đọc nhầm cột, có trường hợp báo nợ **9,17 tỷ** trong khi
   thực tế **0,61 tỷ** (sai 4–15 lần tùy trường hợp). Chuyển sang gọi trực tiếp báo cáo gốc của DNH.
6. **Chatbot trả lời doanh thu gấp đôi thực tế** — 5,09 tỷ thay vì 2,54 tỷ, do hai tiến trình đồng bộ
   chạy chồng nhau ghi trùng dữ liệu. Đã sửa cả triệu chứng lẫn gốc rễ.
7. **Cảnh báo gửi trùng hai lần** — tiến trình tự khởi động lại trùng đúng chu kỳ quét. Đã thêm cơ chế
   khóa chống trùng.
8. **Tồn kho ETC sai đơn vị đo** khiến vận tốc bán sai bản chất.
9. **Cây doanh thu miền Nam thiếu hai đơn vị** *(mới)* — "Kênh MT" và "Chợ sỉ" không hiện do cách tổ
   chức dữ liệu khác các đội thường, làm hụt 6,79 tỷ chỉ tiêu miền Nam.

**Ngoài ra, đã truy ra nguyên nhân hai chênh lệch còn treo từ buổi họp trước** — cả hai nay đã đóng:
- **1,75 tỷ**: không phải lỗi — là phần chỉ tiêu cá nhân của các quản lý vừa quản đội vừa tự phụ trách
  địa bàn, hoàn toàn hợp lệ. Kiểm chứng khớp báo cáo gốc 0 đồng cả 3 miền, bền qua 7 tháng liên tiếp.
- **1,13 tỷ**: chính là lỗi số 2 ở trên.

### C. Công nợ trên chatbot — đã về cùng một nguồn với báo cáo ⭐

Rủi ro lớn nhất còn lại: chatbot và báo cáo trả lời công nợ từ **hai nguồn khác nhau**. Chatbot đọc
bảng nhập tay một lần từ đầu dự án, không tự làm mới.

Đã chuyển chatbot sang đọc trực tiếp **báo cáo công nợ gốc của DNH** — cùng nguồn với báo cáo định kỳ.

| Kiểm chứng | Kết quả |
|---|---|
| Đối chiếu chatbot ↔ báo cáo gốc | ✅ **Lệch 0 đồng** (180,48 tỷ dư nợ · 77,07 tỷ quá hạn) |
| Số dòng dữ liệu | 9.787 khách hàng × kênh |
| Trường hợp cụ thể (BV Đa khoa Đồng Tháp) | ✅ Ra số cụ thể, trước báo "chưa có dữ liệu" |

Đồng thời **chặn cứng đường quay lại nguồn cũ** ở ba lớp. **→ Câu hỏi công nợ nay đủ tin cậy để đưa
vào Demo #1** — đây là câu ban lãnh đạo chắc chắn hỏi.

### D. Chuẩn hóa lương thưởng theo văn bản chính sách của DNH

- **Xác định ngưỡng thật theo từng vai trò** (trước là số tự đặt không căn cứ): nhân viên bán hàng
  **65%**, cấp quản lý **70%** — đối chiếu trực tiếp bảng cấu hình mà hệ thống tính lương của DNH đang
  dùng, kèm các quyết định có chữ ký.
- **Tách bạch ba khái niệm** từng bị gộp làm một, khiến báo cáo tự mâu thuẫn:

  | Khái niệm | Mốc |
  |---|---|
  | Đạt chỉ tiêu | ≥100% |
  | Đạt KPI | ≥80% |
  | Tới mức thưởng nhóm hàng | 65% (nhân viên) / 70% (quản lý) |

- **Cấm hệ thống kết luận "không được thưởng"** khi một người chỉ dưới mốc thưởng nhóm hàng — DNH còn
  nhiều khoản thưởng khác với mốc riêng, và lương cơ bản từ 60% trở lên vẫn hưởng đủ.

### E. Bảo mật — bịt 3 lỗ hổng phân quyền

Tất cả đều do MCNA tự rà soát phát hiện:

1. **Quản lý vùng xem được hiệu suất cá nhân của đội khác** — đã chặn triệt để, đúng cam kết họp 16/07.
2. **Quản lý vùng xem được doanh thu toàn miền** *(mới)* — hỏi *"doanh thu tháng này"* nhận về doanh
   thu **cả miền** (tổng 10 đội) thay vì riêng đội mình. Nguyên nhân: lớp bảo vệ dựng ở mục 1 chỉ phủ
   nhóm báo cáo KPI, bỏ sót nhóm doanh thu, khách hàng, tồn kho, công nợ. Đã chặn 9 báo cáo theo nguyên
   tắc **thà từ chối còn hơn lộ nhầm** *(hệ quả: xem Trang 4 mục 1)*.
3. **Có thể tự nâng quyền qua báo cáo chi phí AI** *(mới)* — tính năng cho ban điều hành xem chi phí
   toàn công ty có sơ hở: danh tính và vai trò người dùng do phần AI tự khai thay vì máy chủ quyết
   định. Thử nghiệm thật cho thấy tài khoản quản lý vùng có thể đọc lịch sử người khác và xem số liệu
   toàn công ty. Đã sửa để **máy chủ luôn là bên quyết định quyền hạn**; bỏ luôn cách nhận diện quyền
   theo *tên* tài khoản.

Kèm theo: chatbot không còn lộ tên hàm/trường kỹ thuật ra câu trả lời cho người dùng.

### F. Chi phí vận hành AI

- **Đã đo được lần đầu** *(mới)*. Trước đây hệ thống có ghi nhận nhưng **không nối được với người
  dùng**, nên mọi báo cáo đều hiện 0 đồng.
- **Tỷ lệ dữ liệu vào/ra ≈ 8,7 lần** — chi phí bị chi phối bởi phần dữ liệu nạp vào, không phải độ dài
  câu trả lời. Đây là chỗ cần tối ưu để giảm giá.
- Đã áp **giới hạn số câu hỏi/phút** mỗi người và **theo dõi ngân sách theo tháng** để kiểm soát rủi ro.
- ⚠️ **Giá dịch vụ AI tăng ~50% sau 31/08/2026** — bản ước tính go-live sẽ dùng giá sau khuyến mãi.

### G. Chuẩn bị Demo #1 (09/08)

- Kịch bản **17 câu theo 3 vai trò** (ban điều hành / quản lý vùng / quản lý đội) kèm bộ đáp án đối
  chiếu sinh trực tiếp từ hệ thống nguồn.
- **Sửa lỗi có thể làm hỏng buổi demo**: công cụ sinh đáp án mặc định tính "tháng này" = tháng đang
  chạy; chạy sáng 09/08 sẽ ra số của tháng 8 mới 9 ngày, không đối chiếu được với câu hỏi demo (vốn hỏi
  tháng 7). Đã bổ sung tùy chọn ghim kỳ.
- **Bổ sung 2 đáp án còn trống**: top khách hàng theo vùng, tồn kho theo vùng. Riêng tồn kho là **lần
  đầu** số liệu chatbot được đối chiếu độc lập với hệ thống nguồn.

### H. Hạ tầng & quản lý mã nguồn

- Chuyển toàn bộ báo cáo/cảnh báo sang đọc **trực tiếp hệ thống nguồn của DNH**, bỏ lớp lưu trữ trung
  gian từng gây lệch số liệu.
- **Hợp nhất hai kho mã nguồn** từng tồn tại song song, sau khi phát hiện mỗi bên đều có phần việc
  riêng chưa đồng bộ — tránh mất công sức hoặc chạy nhầm phiên bản.
- Đưa vào quản lý phiên bản chính thức toàn bộ phần việc từng chỉ tồn tại trên máy chủ.
- Bỏ hẳn kênh chat Telegram (đã chuyển hoàn toàn qua web).
- Bổ sung nền tảng kiểm soát vận hành đồng bộ dữ liệu + cảnh báo khi tiến trình đồng bộ treo/lỗi.

---

# TRANG 2/4 — Việc đã làm (Người thực hiện: Triệu Đặng)

### A. Bảng điều khiển Chi phí AI & Nhật ký truy vấn cho Ban điều hành ⭐ *(mới)*

Màn hình riêng cho cấp lãnh đạo, xem được **không cần hỏi qua chatbot**:
- Toàn bộ lịch sử câu hỏi của mọi nhân viên, dạng dòng thời gian
- Chi phí AI toàn công ty, quy đổi sẵn ra tiền Việt
- Lọc theo từng người dùng

Đi kèm phân quyền: nhân viên và quản lý vùng chỉ xem được lịch sử và chi phí **của chính mình**.

### B. Sửa lỗi dữ liệu

1. **Sửa cột xác định nhân viên trên hóa đơn** — hệ thống từng dùng nhầm cột, gán sai doanh số cho một
   số nhân viên bán hàng.
2. **Bổ sung tra cứu tên nhân viên dự phòng** — một số nhân viên thiếu tên trong danh mục chính, nay tự
   động tra từ nguồn dự phòng thay vì hiện mã trống.
3. **Doanh thu theo vùng không tách được kênh** *(mới)* — trước luôn gộp OTC + ETC. Riêng ETC miền Nam
   lên tới 18,76 tỷ (do một vài bệnh viện/gói thầu lớn), nên câu hỏi "doanh thu OTC theo vùng" có thể
   bị thổi phồng ~4 lần nếu không tách.
4. **Sửa 5 lỗi trong luồng xử lý dữ liệu** phát hiện qua rà soát.
5. **Khôi phục bước nạp cấu hình bị mất** khi viết lại phần máy chủ cho bảng điều khiển mới — thiếu
   bước này khiến chatbot lỗi ngay ở câu hỏi đầu tiên.

### C. Tính năng & vận hành

- Bổ sung **doanh thu Kênh MT (Modern Trade)** tách riêng trong báo cáo miền Nam.
- **Theo dõi & cảnh báo ngân sách chi phí AI theo tháng**.
- Đồng bộ bảng giá dịch vụ AI theo biểu giá hiện hành và biểu giá sau 31/08.
- Kết nối lại cơ chế tự động cập nhật giao diện web sau khi liên kết cũ bị đứt.

---

# TRANG 3/4 — Việc đang làm, sắp tới & trạng thái

| Việc | Trạng thái | Mốc/Ghi chú |
|---|---|---|
| Kiểm định độ chính xác dữ liệu 4 lớp | ✅ **Xong** | 15/15 hạng mục, lệch 0 đồng |
| Công nợ trên chatbot về cùng nguồn | ✅ **Xong** | Đã chạy trên hệ thống thật, khớp 0 đồng |
| Hai chênh lệch số liệu tồn từ họp 16/07 | ✅ **Đóng cả hai** | 1,75 tỷ: không phải lỗi · 1,13 tỷ: đã sửa |
| Bịt 3 lỗ hổng phân quyền | ✅ **Xong** | Đã kiểm chứng trên hệ thống thật |
| Chuẩn hóa lương thưởng theo văn bản DNH | ✅ **Xong** | Còn chờ DNH xác nhận 1 điểm (Trang 4 mục 4) |
| Bảng điều khiển Chi phí AI | 🟡 Đang làm | Phần máy chủ xong; giao diện chờ cập nhật lần cuối |
| Chuẩn bị Demo #1 Chatbot | 🟡 Đang làm | Kịch bản + đáp án sẵn sàng; đang kiểm chứng từng câu. **Hạn 09/08** |
| Ước tính chi phí AI khi go-live | 🟡 Đang làm | Đã có số đầu tiên; cần thêm vài ngày dữ liệu. **Cam kết tuần 8–10** |
| Nghiệm thu theo lớp cùng khách | ⚪ **Chờ khách** | MCNA đã tự kiểm xong; chờ cấp tài khoản quản lý vùng |
| Chốt các điểm nghiệp vụ còn treo | ⚪ **Chờ khách** | Xem Trang 4 |

**Trọng tâm 2 tuần tới:** hoàn tất kiểm chứng trọn bộ kịch bản Demo #1 trên cả 3 vai trò, chốt ước
tính chi phí AI, tổng duyệt trước **09/08**.

---

# TRANG 4/4 — Điểm nghẽn & đề nghị

| # | Điểm nghẽn | Mức | Đề nghị |
|---|---|---|---|
| 1 | **Quyền xem của quản lý vùng chưa được chốt** *(mới)* — MCNA đã tạm chặn 9 báo cáo với tài khoản quản lý vùng để đảm bảo an toàn, nhưng như vậy họ **chưa hỏi được** về doanh thu, tồn kho, công nợ | 🔴 Cao | **Chốt trước 09/08**: quản lý vùng xem số liệu ở phạm vi *đội của mình* hay *cả miền*? Tồn kho và công nợ có thuộc quyền xem của họ không? Chưa chốt thì tại demo không trình bày được phần đăng nhập vai quản lý vùng |
| 2 | **Chưa có nghiệm thu từng lớp từ khách** → sai lệch (nếu có) sẽ phát hiện muộn | 🔴 Cao | **Đề nghị DNH chỉ định 1–2 quản lý vùng** nhận tài khoản, tự kiểm tra số liệu đội mình. Đã nêu từ họp 16/07, vẫn đang chờ |
| 3 | **2 nhân viên có thể đang bị tính thiếu lương** do dữ liệu gốc đánh dấu sai "trùng lặp" | 🔴 Cao | Đã vá tạm ở tầng hệ thống (báo cáo không còn ảnh hưởng). **Đề nghị bộ phận lương/kế toán đối chiếu 2 mã nhân viên đã gửi và sửa dữ liệu gốc** — MCNA không có quyền và không tự xác nhận số tiền |
| 4 | **Nhiều điểm nghiệp vụ chưa được chốt** (mốc tuổi nợ, nguồn giá tồn kho, ngưỡng cảnh báo, phiên bản văn bản chính sách lương áp dụng cho tháng 7...) → số liệu còn dùng giả định | 🟠 TB | Danh sách đầy đủ kèm bằng chứng số liệu đã gửi; **đề nghị chốt các điểm ưu tiên trước Demo #1** |
| 5 | **Hạ tầng vận hành còn mong manh** *(mới)* — đường kết nối giữa giao diện web và máy chủ đổi địa chỉ mỗi lần khởi động lại, phải sửa tay; nhật ký lỗi bị ghi đè nên khó truy nguyên nhân sự cố | 🟠 TB | Đã ghi nhận đầy đủ; **xử lý dứt điểm trước 09/08** để tránh chatbot gián đoạn giữa buổi demo |
| 6 | **Chi phí AI sẽ tăng ~50% sau 31/08/2026** do hết giai đoạn khuyến mãi của nhà cung cấp | 🟠 TB | Bản ước tính go-live dùng **giá sau khuyến mãi**; đang tối ưu phần dữ liệu nạp vào để bù lại |

---

## Số liệu hệ thống *(tháng 7/2026, đến 28/07 — đã kiểm định, lệch 0 đồng với nguồn gốc)*

| Chỉ số | Giá trị |
|---|---|
| Doanh thu OTC | 26,51 tỷ đ (7.580 hóa đơn) |
| Doanh thu ETC | 33,09 tỷ đ (774 hóa đơn) |
| **Tổng doanh thu** | **59,59 tỷ đ** |
| Tổng dư nợ | 180,48 tỷ đ |
| Nợ quá hạn | 77,07 tỷ đ (42,7%) |
| Đạt chỉ tiêu tháng (≥100%) | 8/147 |
| Đạt KPI (≥80%) | 24/147 |
| Tới mức thưởng nhóm hàng (≥65%) | 50/147 |
| Mức hoàn thành theo miền | Bắc 53,5% · Nam 50,2% · Trung 47,1% — toàn đội **51,8%** |
| Quy mô đội ngũ | OTC ~150 nhân viên + ~20 quản lý · ETC 277 nhân sự |

> ⚠️ **Cách đọc con số "đạt chỉ tiêu"**: so lũy kế đến nay với chỉ tiêu **cả tháng**. Tháng 7 còn 3
> ngày chưa kết thúc nên tự nhiên thấp — số cuối tháng sẽ cao hơn đáng kể. Tham chiếu các tháng đã
> trọn: tháng 4 đạt 64/150, tháng 5 đạt 19/149, tháng 6 đạt 25/150.

---

*Thông điệp xuyên suốt kỳ báo cáo: hai tuần qua chuyển từ **kiểm định số liệu** sang **bịt các lỗ hổng
còn sót**. Điểm chung của 9 lỗi và 3 lỗ hổng tìm được là **không tự lộ ra khi nhìn báo cáo** — phải rà
soát chủ động mới thấy. Bốn trong số đó chạm trực tiếp tới đánh giá và lương của nhân viên, là loại rủi
ro nếu để tới lúc nghiệm thu mới phát hiện thì rất khó xử lý.*
