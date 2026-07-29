  # Nội dung Báo cáo tiến độ — 30/07/2026

  *Soạn 22/07/2026, **cập nhật 29/07** với phần việc tuần 23–30/07. Bám đúng cấu trúc 6 slide của bản
  báo cáo 16/07 (Google Slides) để tái sử dụng template. Số liệu lấy tại 29/07 — **các ô đánh dấu 🔄 cần
  chạy lại ngay trước buổi họp** (dữ liệu thay đổi hằng ngày; xem mục "Lệnh lấy số liệu" ở cuối file).*

  > **Kỳ báo cáo: 16/07 → 30/07** (2 tuần, kể từ buổi họp 16/07). Tổng kết cả kỳ: **15/15 hạng mục kiểm
  > định đạt · 10 lỗi số liệu đã sửa · 3 lỗ hổng phân quyền đã bịt** — tất cả do MCNA tự rà soát phát
  > hiện. Xem [`checklist_bao_cao_30-07.md`](checklist_bao_cao_30-07.md) cho việc cần làm sáng 30/07.

  ---

  ## SLIDE 1 — Title

  > **BÁO CÁO TIẾN ĐỘ DỰ ÁN**
  > Xây dựng hệ thống cảnh báo kinh doanh, báo cáo định kỳ và AI chatbot cho nội bộ doanh nghiệp
  > **Dược Nam Hà (DNH)**
  >
  > Progress Update
  > **Ngày báo cáo: 30/07/2026**

  ---

  ## SLIDE 2 — TIMELINE (High-level)

  **Đổi mốc "HÔM NAY" → T5 (27/07 – 02/08)**

  | Giai đoạn | Nội dung | Trạng thái |
  |---|---|---|
  | **GĐ1 — Khảo sát & Chuẩn bị** | Bravo, VPN, khảo sát & ETL dữ liệu mẫu | ✅ **Hoàn tất** |
  | **GĐ2 — Phát triển AI Chatbot** | AI Engine, System Prompt, UI, Security | 🔵 **Đang triển khai** (giai đoạn cuối) |
  | **GĐ3 — UAT & Nghiệm thu Phase 1** | Demo #1, UAT, đào tạo & nghiệm thu | 🟡 Sắp bắt đầu — **Demo #1: 09/08 (T6)** |
  | **GĐ4 — Báo cáo & Go-Live Phase 2** | Cảnh báo Outlook, Demo #2, UAT, Go-Live | ⚡ **Đã hoàn thành phần lớn TRƯỚC HẠN** (kế hoạch T8–T11) |
  | **GĐ5 — Hypercare & Đóng dự án** | Theo dõi vận hành, đóng dự án | ⚪ Chưa tới |

  **Thông điệp chính của slide:**
  > Khối lượng kỹ thuật **đang đi trước kế hoạch** — hệ thống báo cáo & cảnh báo (vốn thuộc Giai đoạn 4,
  > dự kiến tháng 8–9) đã chạy thật trên dữ liệu Bravo từ giữa tháng 7.
  > Điểm cần DNH phối hợp: **nghiệm thu theo lớp** và **xác nhận các quy ước nghiệp vụ**.

  ---

  ## SLIDE 3 — Nhật ký công việc (1/2): Nền tảng dữ liệu

  **Kỳ 15/07 – 30/07/2026**

  ### Chuyển toàn bộ sang đọc trực tiếp Bravo
  Bỏ hẳn lớp lưu trữ trung gian cho luồng báo cáo/cảnh báo — số liệu nay lấy thẳng từ Bravo theo thời
  gian thực, hết độ trễ và sai lệch do đồng bộ.

  ### Kiểm tra chất lượng dữ liệu theo 4 lớp *(đúng mô hình anh Long yêu cầu)*
  Kiểm **từ dưới lên**: cá nhân → quản lý → vùng → toàn công ty, vì lỗi ở lớp dưới sẽ lan lên trên.

  | Lớp | Phạm vi kiểm | Kết quả |
  |---|---|---|
  | Lớp 4 — Cá nhân | Doanh số từng TDV | ✅ Đúng |
  | Lớp 3 — Quản lý | Tổng đội từng QLV | ✅ Khớp tuyệt đối tổng TDV dưới quyền |
  | Lớp 2 — Vùng | Doanh thu & công nợ theo miền | ✅ Khớp tổng, **lệch 0 đồng** |
  | Lớp 1 — Toàn công ty | Doanh thu, công nợ, KPI, tồn kho | ✅ Khớp hóa đơn gốc Bravo |

  **→ 15/15 hạng mục đạt, sai lệch 0 đồng ở mọi ranh giới giữa các lớp.**

  ### 6 lỗi thật phát hiện & sửa nhờ quy trình này

  **① Tỷ lệ nợ quá hạn 92,9% / 81,1% mà DNH phản ánh — xác nhận là LỖI THẬT, đã sửa.**
  Công thức cũ đọc cột "đã thanh toán" bị đứng yên (không ghi nhận khoản trả sau, không đối trừ ứng
  trước). Ví dụ: FPT Long Châu bị báo nợ **9,17 tỷ** trong khi thực tế chỉ **0,61 tỷ**. Nay gọi trực
  tiếp báo cáo công nợ gốc của DNH.

  | Kênh | Tỷ lệ quá hạn (sai → đúng) |
  |---|---|
  | OTC | 92,9% → **39,4%** |
  | ETC | 81,1% → **52,3%** |

  **② Hai quản lý bị hệ thống gắn nhầm cờ "trùng lặp"** — khiến doanh số và **cả đội dưới quyền họ**
  (≈1,55 tỷ + ≈389 triệu/tháng) biến mất khỏi mọi báo cáo KPI. Đã vá tạm để báo cáo chạy đúng; **cần
  DNH sửa dữ liệu gốc**.

  **③ Nhóm khách hàng thiếu hồ sơ vùng** khiến **2,1 tỷ** doanh thu không được tính vào đúng miền.

  **④ Chỉ tiêu tháng bị lấy nhầm của tháng khác** *(mới, tuần 23–30/07)* — khi xem doanh số theo từng
  ngày của một nhân viên, hệ thống lấy chỉ tiêu **cao nhất trong 3 tháng gần nhất** thay vì chỉ tiêu của
  đúng tháng đang xem. Trên một nhân viên thật: lấy 343,7 triệu (của tháng 4) thay vì 302,2 triệu của
  tháng 7.

  | | Trước khi sửa | Sau khi sửa |
  |---|---|---|
  | Mức hoàn thành tháng | 65,2% | **74,1%** |
  | Số ngày bị chấm Đỏ | 11 | **10** |

  Nhân viên bị báo thấp hơn thực tế **9 điểm %**, 3 ngày bị chấm màu xấu oan. Lỗi áp dụng cho **mọi nhân
  viên bán hàng**. Đây cũng chính là nguyên nhân **chênh lệch 1,13 tỷ** còn treo từ buổi họp trước.

  **⑤ Hai đơn vị kinh doanh miền Nam biến mất khỏi báo cáo KPI** *(mới)* — "Kênh MT" và "Chợ sỉ" không
  hiện trong danh sách quản lý vùng do cách tổ chức dữ liệu khác các đội thường, làm **hụt 6,79 tỷ** chỉ
  tiêu miền Nam.

  **⑥ Số liệu KPI toàn công ty chỉ gồm MỘT miền mà không hề báo lỗi** *(mới, 29/07 — nghiêm trọng nhất)*

  DNH **không ghi số liệu tháng thành một lần**, mà tách ra nhiều ngày theo từng miền. Tháng 7 có 2 đợt
  ghi: ngày 27/07 ghi miền Bắc + miền Nam, ngày 28/07 chỉ ghi miền Trung.

  Hệ thống trước đây luôn lấy **đợt ghi mới nhất** làm số liệu tháng — nên tra ngày 29/07 chỉ thấy miền
  Trung, và báo *"toàn đội đạt 48,7%"* trong khi đó thực chất chỉ là miền Trung. **Thiếu hẳn 43,97 tỷ chỉ
  tiêu của hai miền còn lại.**

  Nguy hiểm ở chỗ **không có cảnh báo nào**: lưới kiểm tra chéo chỉ đối chiếu các miền *có mặt* trong kết
  quả, nên miền biến mất hoàn toàn thì không có gì để đối chiếu. Con số ra tròn trịa và tự tin.

  | | Trước khi sửa | Sau khi sửa |
  |---|---|---|
  | Số nhân viên tính KPI | 29 người | **147 người** |
  | Miền có trong báo cáo | Chỉ miền Trung | **Đủ 3 miền** |
  | Tổng chỉ tiêu toàn công ty | 7,00 tỷ | **50,97 tỷ** |

  **Đã sửa ở cả 3 hệ thống** (chatbot, báo cáo email, công cụ đối chiếu): gộp số liệu theo **tháng** thay
  vì theo một ngày, mỗi nhân viên lấy bản ghi mới nhất của chính họ. Kiểm chứng: tổng chỉ tiêu ra đúng
  **50.967.586.921đ**, khớp từng đồng với giá trị đã xác nhận trước đó. Đồng thời bổ sung cảnh báo bắt
  buộc khi phát hiện thiếu miền.

  ### Hai chênh lệch còn treo từ buổi họp 16/07 — đã đóng cả hai

  | Chênh lệch | Kết luận |
  |---|---|
  | **1,75 tỷ** (chỉ tiêu miền Bắc) | **Không phải lỗi** — là phần chỉ tiêu cá nhân của các quản lý vừa quản đội vừa tự phụ trách địa bàn, hoàn toàn hợp lệ. Kiểm chứng khớp báo cáo gốc **0 đồng** cả 3 miền, bền qua **7 tháng liên tiếp** |
  | **1,13 tỷ** (chỉ tiêu một quản lý) | Chính là lỗi ④ ở trên, đã sửa |

  *Đồng thời điều này cũng bác bỏ nghi vấn "chỉ tiêu cấp vùng cộng chồng lên chỉ tiêu cá nhân" ở mức số
  học — tổng gộp khớp tuyệt đối với bảng chỉ tiêu vùng chính thức của DNH.*

  ---

  ## SLIDE 4 — Nhật ký công việc (2/2): Chatbot & Báo cáo

  **Kỳ 15/07 – 30/07/2026**

  ### ⭐ Công nợ trên chatbot — đã về cùng một nguồn với báo cáo *(mới, tuần 23–30/07)*

  Rủi ro lớn nhất còn lại sau họp 16/07: chatbot và báo cáo trả lời công nợ từ **hai nguồn khác nhau**.
  Chatbot đọc bảng nhập tay một lần từ đầu dự án, không tự làm mới — chính nguồn gây ra con số 9,17 tỷ
  ở lỗi ① slide trước. Nay chatbot đọc **trực tiếp báo cáo công nợ gốc của DNH**.

  | Kiểm chứng | Kết quả |
  |---|---|
  | Đối chiếu chatbot ↔ báo cáo gốc | ✅ **Lệch 0 đồng** (180,48 tỷ dư nợ · 77,07 tỷ quá hạn) |
  | Số dòng dữ liệu | 9.787 khách hàng × kênh |

  Đồng thời **chặn cứng đường quay lại nguồn cũ** ở ba lớp. **→ Câu hỏi công nợ nay đủ tin cậy để đưa
  vào Demo #1** — đây là câu ban lãnh đạo chắc chắn hỏi.

  ### AI Chatbot (Giai đoạn 2)
  - **Phân quyền theo vùng đã áp dụng thật ở tầng code** — mỗi tài khoản chỉ truy vấn được đúng
    vùng/kênh của mình, không phụ thuộc vào việc AI có "tự giác" lọc hay không.
    *(Đáp ứng trực tiếp yêu cầu tại họp 16/07: mỗi QLV chỉ tự kiểm tra vùng mình.)*
  - **Bịt thêm 2 lỗ hổng phân quyền** *(mới)*, cả hai do MCNA tự rà soát phát hiện:
    - *Quản lý vùng xem được doanh thu toàn miền* — hỏi "doanh thu tháng này" nhận về doanh thu **cả
      miền** (tổng 10 đội) thay vì riêng đội mình. Lớp bảo vệ dựng trước đó chỉ phủ nhóm báo cáo KPI, bỏ
      sót nhóm doanh thu/khách hàng/tồn kho/công nợ. Đã chặn theo nguyên tắc **thà từ chối còn hơn lộ
      nhầm** *(hệ quả cần DNH chốt — xem Slide 6)*.
    - *Có thể tự nâng quyền qua báo cáo chi phí AI* — danh tính và vai trò người dùng do phần AI tự khai
      thay vì máy chủ quyết định. Đã sửa để **máy chủ luôn là bên quyết định quyền hạn**.
  - **Cảnh báo khi dữ liệu có thể cũ** — phát hiện tiến trình đồng bộ treo, thay vì trả lời tự tin
    bằng số liệu cũ.
  - **Cảnh báo khi số liệu không khớp** — nếu tổng theo vùng lệch tổng chung, chatbot **nói rõ với
    người dùng** thay vì im lặng đưa số sai.
  - **Giới hạn 10 câu hỏi/phút/người** — kiểm soát chi phí API *(đúng mối lo anh Long nêu ở họp 16/07
    về chi phí khi 10–20 người dùng đồng thời)*.
  - **Sửa lỗi dữ liệu nhân đôi**: doanh thu chatbot từng báo gấp 2 lần thật; đã truy ra nguyên nhân và
    xử lý — nay **khớp Bravo lệch 0 đồng**.

  ### Báo cáo định kỳ (Giai đoạn 4 — làm sớm)
  - **Thêm "Chi tiết KPI theo Vùng – QLV – TDV"** — thể hiện đúng mô hình 4 lớp; quản lý vùng thấy
    từng QLV và từng TDV dưới quyền.
  - **Thêm "Doanh số ETC theo nhân viên"** — trước đây kênh ETC hoàn toàn không có báo cáo nhân sự.
  - **Sửa lỗi cộng trùng KPI**: chỉ tiêu/doanh số từng bị cộng gấp đôi do gộp nhầm 2 tầng TDV và QLV
    (vốn là 2 cách cắt lát của cùng một khoản doanh thu).
  - **Nhãn kỳ báo cáo trung thực hơn**: hiển thị đúng khoảng đã có dữ liệu thay vì cả khung lịch.

  ### Chuẩn hóa lương thưởng theo văn bản chính sách của DNH *(mới)*

  Ngưỡng đánh giá trước đây là **số MCNA tự đặt, không có căn cứ**. Nay đối chiếu trực tiếp bảng cấu
  hình mà hệ thống tính lương của DNH đang dùng, kèm các quyết định có chữ ký — và **tách bạch ba khái
  niệm** từng bị gộp làm một khiến báo cáo tự mâu thuẫn:

  | Khái niệm | Mốc |
  |---|---|
  | Đạt chỉ tiêu | ≥100% |
  | Đạt KPI | ≥80% |
  | Tới mức thưởng nhóm hàng | **65%** (nhân viên) / **70%** (quản lý) |

  Đồng thời **cấm hệ thống kết luận "không được thưởng"** khi một người chỉ dưới mốc thưởng nhóm hàng —
  DNH còn nhiều khoản thưởng khác với mốc riêng, và lương cơ bản từ 60% trở lên vẫn hưởng đủ.

  ### Chi phí vận hành AI — đã đo được lần đầu *(mới)*

  Trước đây hệ thống có ghi nhận chi phí nhưng **không nối được với người dùng**, nên mọi báo cáo đều
  hiện 0 đồng. Đã sửa và bắt đầu có số thật.

  - Bổ sung **Bảng điều khiển Chi phí AI & Nhật ký truy vấn** cho Ban điều hành: xem lịch sử câu hỏi của
    mọi nhân viên và chi phí toàn công ty (quy đổi sẵn ra tiền Việt), **không cần hỏi qua chatbot**.
  - **Tỷ lệ dữ liệu vào/ra ≈ 8,7 lần** — chi phí bị chi phối bởi phần dữ liệu nạp vào, không phải độ dài
    câu trả lời. Đây là chỗ đang tối ưu để giảm giá.
  - ⚠️ **Giá dịch vụ AI tăng ~50% sau 31/08/2026** — bản ước tính go-live sẽ dùng giá sau khuyến mãi.

  ---

  ## SLIDE 5 — OVERALL STATUS UPDATE

  ### VIỆC ĐANG LÀM / SẮP TỚI

  - ✅ **Demo #1 Chatbot (09/08) — ĐÃ KIỂM CHỨNG TRỌN BỘ.** Ngày 29/07 chạy đủ **17 câu trên hệ thống
    thật, 17/17 đạt**, cả 3 vai trò (Ban điều hành / Giám đốc miền / Quản lý vùng), đối chiếu từng con
    số với dữ liệu gốc Bravo. Trong đó **3 câu thử bảo mật đều bị chặn đúng** (hỏi vùng khác, tra bảng
    dữ liệu đã ngừng dùng, xem ngoài phạm vi đội).
  - 🔴 **MỚI — cần DNH chốt trước 09/08: quyền xem của quản lý vùng.** Sau khi bịt lỗ hổng, MCNA đã tạm
    chặn 9 báo cáo với tài khoản quản lý vùng để đảm bảo an toàn. Hệ quả: họ **chưa hỏi được** về doanh
    thu, tồn kho, công nợ. Cần chốt: quản lý vùng xem số liệu ở phạm vi *đội của mình* hay *cả miền*?
    Tồn kho và công nợ có thuộc quyền xem của họ không?
  - **Chờ DNH xác nhận các điểm nghiệp vụ còn lại** *(đã gửi danh sách kèm bằng chứng số liệu)*:
    1. ✅ ~~Cách tính ngày quá hạn & xác nhận báo cáo công nợ chuẩn~~ — **đã tự giải quyết**: chatbot và
      báo cáo nay dùng chung báo cáo gốc của DNH
    2. Mốc phân nhóm tuổi nợ
    3. Nguồn giá để tính giá trị tồn kho *(thiếu nên mục "tồn kho chết" luôn hiển thị 0)*
    4. ✅ ~~Chỉ tiêu cấp vùng vs cá nhân~~ — **đã bác bỏ nghi vấn cộng chồng** ở mức số học (Slide 3);
      vẫn nên xác nhận về mặt tổ chức nhân sự
    5. Kênh ETC có giao chỉ tiêu theo từng nhân viên không
    6. Phiên bản văn bản chính sách lương áp dụng cho tháng 7 *(có 2 bản cùng tồn tại)*
  - **Đề nghị DNH nghiệm thu theo từng lớp dữ liệu** — MCNA đã tự kiểm xong (bước 1–2); chờ anh Long
    khảo sát (bước 3) và quản lý vùng chéo kiểm (bước 4).
  - **Cần danh sách tài khoản Chatbot thật** để cấp quyền cho quản lý vùng tự kiểm tra.
  - Chuẩn bị **ước tính chi phí go-live** (cam kết tuần 8–10).

  ### MILESTONES

  | Mốc | Hạn | Trạng thái |
  |---|---|---|
  | **M1 — Dữ liệu + AI Engine sẵn sàng** | 19/07 | ✅ Kỹ thuật hoàn thành — **chờ DNH nghiệm thu** |
  | **M2 — Demo #1 Chatbot** | 09/08 | 🔵 Đang chuẩn bị |
  | **M4 — Demo #2 Cảnh báo Outlook** | 06/09 | ⚡ Nội dung đã sẵn sàng sớm |
  | **Đóng dự án** | 30/09 | ⚪ |

  ### 🔄 Số liệu hệ thống đang vận hành *(cập nhật 29/07 — chạy lại trước buổi họp)*

  | Chỉ số | Giá trị (tháng 7, đến 29/07) |
  |---|---|
  | Doanh thu OTC | 27,64 tỷ đ (8.006 hóa đơn) |
  | Doanh thu ETC | 33,63 tỷ đ (799 hóa đơn) |
  | **Tổng doanh thu** | **61,27 tỷ đ** |
  | Tổng dư nợ / quá hạn | 177,88 tỷ / 75,65 tỷ (**42,5%**) |
  | Đạt chỉ tiêu (≥100%) · Đạt KPI (≥80%) · Tới mức thưởng (≥65%) | **8/147 · 25/147 · 50/147** |
  | Mức hoàn thành theo miền | Bắc 53,5% · Nam 50,2% · Trung 48,7% — toàn đội **52,0%** |

  > ⚠️ **Cách đọc con số "đạt chỉ tiêu"**: so lũy kế đến nay với chỉ tiêu **cả tháng**. Tháng 7 còn 3
  > ngày chưa kết thúc nên tự nhiên thấp — số cuối tháng sẽ cao hơn đáng kể. Tham chiếu các tháng đã
  > trọn: tháng 4 đạt **64/150**, tháng 5 đạt **19/149**, tháng 6 đạt **25/150**.

  ---

  ## SLIDE 6 — RISK & MITIGATION

  | # | Rủi ro | Mức | Biện pháp xử lý |
  |---|---|---|---|
  | 1 | 🆕 **Quyền xem của quản lý vùng chưa được chốt** — đã tạm chặn 9 báo cáo để đảm bảo an toàn, nhưng như vậy quản lý vùng chưa hỏi được về doanh thu, tồn kho, công nợ | 🔴 Cao | **Đề nghị chốt trước 09/08**. Chưa chốt thì tại Demo #1 không trình bày được phần đăng nhập vai quản lý vùng — vốn là phần thể hiện năng lực phân quyền |
  | 2 | **Các điểm nghiệp vụ chưa được DNH chốt** → số liệu còn dùng giả định, rủi ro phải làm lại sau Demo | 🔴 Cao | Đã lập danh sách kèm bằng chứng; **2/5 điểm ưu tiên đã tự giải quyết** trong kỳ này (công nợ, chỉ tiêu vùng); đề nghị chốt phần còn lại trước 09/08 |
  | 3 | **Chưa có nghiệm thu từng lớp từ DNH** → sai lệch phát hiện muộn, tốn công sửa lại cuối dự án | 🔴 Cao | Mời anh Long soát Lớp 1–2 trước; **cấp tài khoản để QLV vùng tự kiểm Lớp 3–4** *(đã nêu từ 16/07, vẫn đang chờ)* |
  | 4 | **Dữ liệu gốc Bravo có cờ/mã sai** — 2 quản lý thật bị ẩn khỏi báo cáo, 6 mã nhân viên không xác định ≈484 triệu | 🟠 TB | Đã vá tạm ở tầng code. ⚠️ **Phát hiện thêm**: cờ sai này còn tác động vào **chính thủ tục tính lương** của DNH, nên 2 người có thể đang bị tính thiếu thưởng thật — đề nghị bộ phận lương/kế toán đối chiếu và sửa dữ liệu gốc |
  | 5 | **Chi phí token AI** khi 10–20 người dùng đồng thời | 🟠 TB | Đã áp giới hạn 10 câu/phút/người + theo dõi ngân sách theo tháng; **đã đo được số thật lần đầu**; cam kết ước tính chi phí tuần 8–10 |
  | 6 | 🆕 **Chi phí AI tăng ~50% sau 31/08/2026** do hết giai đoạn khuyến mãi của nhà cung cấp | 🟠 TB | Bản ước tính go-live dùng **giá sau khuyến mãi**; đang tối ưu phần dữ liệu nạp vào để bù lại |
  | 7 | 🆕 **Hạ tầng vận hành còn mong manh** — đường kết nối giữa giao diện web và máy chủ đổi địa chỉ mỗi lần khởi động lại, phải sửa tay | 🟠 TB | Đã ghi nhận đầy đủ; **xử lý dứt điểm trước 09/08** để tránh chatbot gián đoạn giữa buổi demo |

  ---

  ## SLIDE 7 — Kết

  > Cảm ơn đã lắng nghe
  > **MCNA Technology**

  ---

  ## Ghi chú khi dựng slide

  - **Giữ nguyên template & bố cục** bản 16/07 để nhất quán, chỉ thay nội dung.
  - **Slide 2**: nhớ dời dải "HÔM NAY" sang **T5 (27/07–02/08)** và đổi màu trạng thái 5 giai đoạn.
  - **Không đưa tên nhân viên cụ thể** lên slide chiếu chung ở phần lỗi dữ liệu (mục ②, ④) — chỉ nói
    "2 quản lý" / "một nhân viên"; danh tính đã có trong tài liệu gửi riêng.
  - **Slide 3 nay có 5 lỗi thay vì 3** — nếu chật chỗ, gộp ④⑤ thành một khối "phát hiện thêm tuần
    23–30/07" và để bảng so sánh 65,2% → 74,1% làm điểm nhấn (đây là ví dụ dễ hiểu nhất cho khách về
    việc lỗi âm thầm ảnh hưởng tới đánh giá nhân viên).
  - **Slide 6 nay có 7 rủi ro** — 3 mục đánh 🆕 là mới phát sinh trong kỳ. Mục 1 nên nói trước vì đang
    chặn Demo #1 và cần DNH quyết ngay tại buổi họp.
  - Phần nhật ký (slide 3–4) nên để dạng **bảng/gạch đầu dòng ngắn**, số liệu in đậm — bản 16/07
    dùng bảng, giữ vậy cho quen mắt.

  ## Lệnh lấy lại số liệu trước buổi họp

  Chạy trong `D:\DNH` — công cụ này sinh **toàn bộ** số cần cho slide, cùng nguồn với đáp án Demo #1:

  ```bash
  set PYTHONIOENCODING=utf-8 && python scripts/demo1_ground_truth.py
  ```

  Đối chiếu output với bảng số liệu Slide 5:

  | Lấy từ mục | Điền vào |
  |---|---|
  | `[C1]` | Doanh thu OTC / ETC / Tổng + số hóa đơn |
  | `CÔNG NỢ` dòng `TOÀN CÔNG TY` | Tổng dư nợ · quá hạn · % |
  | `[C7]` | 3 mốc: ≥100% · ≥80% · ≥65% |
  | `[C6]` | Mức hoàn thành 3 miền + toàn đội |

  > ⚠️ **Không dùng cờ `--as-of`** cho báo cáo tiến độ — cờ đó chỉ dành cho việc tập dượt Demo #1 với
  > tháng 7 đã trọn. Báo cáo 30/07 cần số thực tế đến đúng ngày họp.

  **Số chi phí AI**: hỏi chatbot bằng tài khoản `dnh`, phiên chat mới — *"Báo cáo chi phí AI toàn công
  ty"*. Lưu ý khi trình bày: chi phí chỉ tính được cho các phiên **từ 28/07 trở đi** (trước đó hệ thống
  không nối được chi phí với người dùng), đừng để khách hiểu nhầm là chi phí cả dự án thấp như vậy.
