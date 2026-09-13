# Kế hoạch chốt UAT và Go-live chatbot DNH — 11–20/09/2026

Lập lúc khoảng 09:05 ngày 11/09/2026, giờ Việt Nam. Theo biên bản họp 10/09, lịch Go-live 20/09 và đóng dự án 30/09. Đây là kế hoạch thực hiện; các ô chưa đánh dấu không phải công việc đã hoàn thành.

## 1. Đích đến và trạng thái xuất phát

**Đích đến: tất cả 126 câu còn trong phạm vi được trả lời đúng theo tiêu chí đã thống nhất, trên bản triển khai được kiểm chứng.** Không cam kết có số liệu cho nguồn chưa tồn tại; câu thiếu nguồn chỉ đạt khi đã xác nhận giới hạn nguồn, trả đúng phần có thể kiểm chứng và không bịa số.

| Phạm vi | Tổng câu giữ lại | Đang được ghi nhận đạt | Còn cần chốt |
|---|---:|---:|---:|
| C-Level | 46 | 30 | 16 |
| Giám đốc miền/kênh | 42 | 25 | 17 |
| QLV | 38 | 17 | 21 |
| Tổng | 126 | 72 | 54 |

Nguồn: lần đọc tab UAT SQL sáng 11/09 tại [bảng UAT](https://docs.google.com/spreadsheets/d/1BrvnWvDCTKFnLw3HGcIl6Vp3VHoDSwmy6BhAsRMATPM/edit?gid=1928331201#gid=1928331201).

- 72/126 = **57,14% ghi nhận trên sheet**, chưa phải tỷ lệ đã tái chứng nhận độc lập trên bản cuối. Cách tổng hợp hiện tại lấy hợp của kết quả chạy ghi khớp và cột chốt ghi đạt, không đếm hai lần. Những dòng “khớp, tuy nhiên…” phải đọc hết trước khi chốt chính thức.
- 9 câu đã loại về dự báo/lợi nhuận: C04, C14, C15, C19, C50, C51, M39, M43, V09. 3 câu tạm loại: C25, C49, V16. Giữ lịch sử và lý do; không xóa hàng.
- Không dùng mẫu số 119 trong tài liệu cũ. Không loại thêm câu khó để tăng phần trăm. Mọi thay đổi phạm vi sau hôm nay phải được PMO/người phụ trách UAT duyệt và báo cả trước/sau thay đổi.
- Trên 95% của 126 câu cần tối thiểu **120/126**. Đây chỉ là mốc tỷ lệ, **không phải hoàn thành yêu cầu trả lời đúng tất cả**. Đích hoàn thành vẫn là 126/126, không còn lỗi Critical/High hoặc rò quyền.
- V07 và V08 hiện đã ghi khớp: đưa vào kiểm hồi quy, không mặc định xếp lại thành lỗi cần sửa.

### Bằng chứng kỹ thuật đang có

- Repo đang ở `f692e45`. Theo log anh gửi, máy 24 đã kéo cùng commit và dịch vụ đã chạy lại, health trả `ok`.
- Lần kiểm toàn bộ test local đã ghi nhận 558 passed, 1 deselected. Phải ghi lý do test bị loại trước khi dùng số này làm bằng chứng nghiệm thu.
- Bộ kiểm định tuyến đã duyệt 138 câu; 3 câu dự báo C50/M43/V09 nằm ngoài đường ép công cụ nghiệp vụ. Định tuyến đúng không chứng minh câu trả lời đúng.
- Hai file backend trên máy 24 đã được đưa vào stash `backup-machine24-before-f692e45-20260911`. Phải đối chiếu bản vá trong đó; không mặc định mọi sửa đổi đều đã lên Git, không chạy `stash pop` hàng loạt.

## 2. Định nghĩa đạt — khóa trước khi chạy

Mỗi câu phải qua toàn bộ các mục sau:

1. **Đúng nội dung:** trả đủ các ý bắt buộc của câu hỏi; danh sách mẫu phải nói rõ là mẫu và có cách lấy danh sách đầy đủ nếu đó là yêu cầu chính.
2. **Đúng dữ liệu:** tiền, khách, đơn, SKU, tỷ lệ và tổng đối soát khớp nguồn độc lập. So số gốc trước làm tròn; không lấy hai công cụ dùng cùng một hàm làm hai nguồn xác nhận độc lập.
3. **Đúng kỳ:** ngày đầu/cuối, tháng đã tròn, MTD và kỳ so sánh rõ ràng. Không tự đổi “tháng này” thành tháng trước. Chốt dữ liệu tại cùng một mốc để tránh lệch do đồng bộ trong lúc kiểm.
4. **Đúng phạm vi:** đúng vai, vùng, kênh, đội và lịch sử thành phần đội. Không mở quyền lương hoặc free-SQL chỉ để một câu được trả lời.
5. **Đúng giới hạn:** không biến thiếu dữ liệu thành 0; không gọi ngày cuối tháng là đã chốt lương nếu không có bằng chứng; không gọi lịch sử mua là nhu cầu chắc chắn hoặc doanh thu chắc chắn mất.
6. **Chạy được trên chatbot:** không lỗi SQL, cạn tool, mất streaming hay cắt mất phần trả lời trọng tâm. Báo cáo dài phải có phân trang/xuất đầy đủ, không chỉ tăng giới hạn token.
7. **Có bằng chứng:** tài khoản/vai, kỳ, commit, thời điểm sync, câu trả lời, tên công cụ, SQL hoặc nguồn đối chứng, chênh lệch và người chấm đều được lưu.

Phân loại kết quả cuối:

- **ĐẠT — đầy đủ dữ liệu:** đáp ứng đủ câu hỏi bằng dữ liệu kiểm chứng được.
- **ĐẠT — giới hạn nguồn/quyền đã xác nhận:** trả đúng phần được phép/có nguồn, ghi rõ phần không thể kết luận; người chấm duyệt cách trả lời này theo rubric.
- **CHƯA ĐẠT:** sai số/sai ý/sai kỳ/sai quyền hoặc từ chối nhầm dù có dữ liệu.
- **CHỜ KIỂM:** đã sửa hoặc chưa có đủ bằng chứng retest; không cộng vào đạt.

Báo cáo tách hai loại đạt để người nhận thấy mức đáp ứng nghiệp vụ thực sự. Không dùng nhãn “thiếu nguồn” khi mới chỉ có một truy vấn rỗng hoặc công cụ bị lỗi.

## 3. Phân công đề xuất và quy tắc phối hợp

| Người/nhóm | Trách nhiệm | Sản phẩm bàn giao |
|---|---|---|
| Đăng | Điều phối kỹ thuật, xác nhận máy 24, điều phối chạy API, duyệt bản triển khai | Bản chạy xác định được commit, lịch deploy, nhật ký chi phí |
| Codex | `backend/`, `src/` và test liên quan | Bản vá theo nguyên nhân, test tái hiện lỗi, kết quả kiểm lại |
| Claude/Antigravity theo phiên được phân công | `scripts/`, SQL đối chứng, tài liệu và đối chiếu Bravo | Query đúng kỳ/phạm vi, bằng chứng số gốc, danh sách lỗi nguồn |
| Đăng — người chấm A | 46 câu C giữ lại + M01–M17 = 63 câu | Kết quả có bằng chứng và tiêu chí từng câu |
| Đồng nghiệp/tester — người chấm B | M18–M44 trừ M39/M43 = 25 câu; 38 câu V = 63 câu | Kết quả có bằng chứng và tiêu chí từng câu |
| Nguyễn Thùy Linh/DNH, cần xác nhận lịch | Xác minh nguồn, quy tắc nghiệp vụ và kiểm độc lập | Xác nhận ngoại lệ, toàn bộ câu chuyển không đạt → đạt và ít nhất 15 câu đạt rải đều ba vai |
| PMO Đặng Việt Triều | Khóa phạm vi, theo dõi phụ thuộc, trình quyết định Go/No-go | Nhật ký quyết định, kế hoạch xử lý rủi ro tiến độ |
| Trần Quang Long/DNH | Xác nhận tài khoản demo, thanh toán API, đầu mối nghiệm thu | Chấp thuận sử dụng thử và phối hợp Go-live |

Phân công là đề xuất cần chốt trong phiên mở việc ngày 11/09; không mặc định DNH hoặc đồng nghiệp đã nhận lịch.

- Một thời điểm chỉ một người sửa cùng một file. Nếu hai cụm đụng `report_templates.py`, bàn giao nối tiếp hoặc tách commit nhỏ và thống nhất vùng sửa.
- Chỉ stage đường dẫn cụ thể. Không kéo theo output/untracked của người khác; không sửa checker để làm đẹp tỷ lệ.
- Reviewer đối chứng không chỉ đọc test do người viết bản vá tạo ra.
- Không deploy khi tester đang chạy vòng đo. Gom thay đổi prompt/mô tả tool theo bản ứng viên để giảm ghi lại cache.
- Không bật lại lịch business-eval tự chạy. Không tăng quota hoặc tạo tài khoản thay thế chỉ để né hạn mức đã áp dụng.

## 4. Danh mục 54 câu cần xử lý — không bỏ sót

“Cần xử lý” có thể là retest bản đã sửa, sửa chatbot, sửa đối chứng đã được chứng minh sai, hoặc xác nhận nguồn. Không mặc định cả 54 câu đều còn lỗi code.

| Cụm / số câu | Mã câu | Việc phải làm và điều kiện chốt | Hạn bản sửa/đối chứng |
|---|---|---|---|
| A. Doanh thu, kỳ, target / 8 | C02, C03, C08, M02, V03, V05, V10, V11 | Chốt biên kỳ; đếm đơn theo khóa thật; target đúng từng tháng/người; YTD không suy ra kế hoạch năm khi thiếu tháng; V03 không bỏ doanh số cuối tuần. Đối soát tổng và chi tiết. | 14/09 trưa |
| B. Nhân sự, KPI, quyền thưởng / 6 | C54, M16, M20, M28, V18, V40 | Roster không hụt đầu tháng; tách thiếu quản lý với thiếu cây cấp trên; kiểm ý nghĩa cờ trùng; M16 trả đủ người thực sự giảm liên tiếp; M20 từ chối đúng phần lương nhưng trả phần KPI; V18 đủ người trong đội. M28 phải đối chiếu đúng câu hỏi, không dùng checker nhân sự thay cho mapping khách hàng. | 14/09 trưa |
| C. Vòng đời, khách hàng, địa bàn / 12 | C20, C28, C30, M22, M23, M24, V15, V21, V23, V24, V26, V28 | Khóa lịch sử tham chiếu độc lập cửa sổ hiển thị; khách duy nhất; nhóm âm/0; NC/RO khác first-observed; đội hiện tại khác đội lịch sử; đủ danh sách địa bàn/khách ưu tiên. | 15/09 trưa |
| D. SKU, nhóm tương đồng, cặp mua / 9 | C34, M25, M32, M33, V25, V29, V30, V31, V32 | Phân biệt ngày ra mắt với lần bán đầu; không tự tạo target SKU; SKU ngừng bán vẫn xuất hiện; peer có tiêu chí; cặp mua đếm đúng khách/đơn; phủ khách khác sản lượng và AOV. | 15/09 chiều |
| E. Khuyến mãi, chiết khấu / 4 | C13, M35, M36, V34 | Kiểm nguồn CTKM mới nhất và DiscountRate thật; không lặp kết luận nguồn chết từ tháng 1 nếu chưa kiểm lại; trả đúng khoảng tháng; không suy diễn uplift nhân quả. | 15/09 chiều |
| F. Tồn kho / 2 | C41, M40 | Đúng kho/vùng, đơn vị tính, tồn hiện tại và tốc độ bán; giá trị thiếu khác 0; đúng nhóm thiếu/chậm/cận hạn; khách gợi ý đúng SKU đang xử lý. | 15/09 chiều |
| G. Công nợ, thu tiền / 8 | C37, C38, C40, M37, M38, V35, V36, V37 | Tách dư nợ hiện tại với lịch sử, thu tiền thật, cam kết và DSO; kiểm S26 nguồn local được cấp quyền; không suy ra tiền thu từ biến động dư nợ. | Chốt nguồn 14/09; trả lời/retest 16/09 |
| H. ETC, hợp đồng / 3 | C43, C44, M42 | Kiểm khóa nối hợp đồng–hóa đơn và giá trị bất thường; thiếu khóa thì từ chối phép gán chắc chắn; tổng kênh vẫn kiểm nếu được phép. | Chốt nguồn 14/09; trả lời/retest 16/09 |
| I. Việc cần làm, người phụ trách / 2 | C52, M44 | Tách gợi ý hành động từ số liệu với action tracker đã giao; không bịa owner/deadline/trạng thái thực hiện. | Chốt nguồn 14/09; trả lời/retest 16/09 |

### Các lỗi chéo cần khóa thành test bắt buộc

- [ ] C29/C31/M08/V15: số khách không đổi khi chỉ mở rộng phần hiển thị; nhóm doanh thu cộng lại bằng biến động tổng; doanh thu âm không bị bỏ im lặng.
- [ ] C02/C03/M02/V03/V11: kỳ so sánh và target đúng tháng; có giao dịch thứ Bảy vẫn tính; ngày tương lai loại theo đúng mốc đang kiểm.
- [ ] M16: phân biệt giảm ba tháng liên tiếp với ba lần giảm rải rác; đủ danh sách, tháng thiếu không tự thành 0 nếu nguồn chưa đầy đủ.
- [ ] C54/M20/V18: danh mục trùng không có nghĩa một người đếm hai lần; 67,6% không được coi đạt ngưỡng 70%; không diễn giải V25=0 là phải bù thưởng khi cơ chế đã đổi.
- [ ] V33: createdAt là thời điểm tạo đơn; chênh ngày hóa đơn không chứng minh giao hàng chậm; số nhóm chồng nhau không cộng thành tổng đơn duy nhất.
- [ ] V38/V39/C41/M40: tồn đầu kỳ khác tồn hiện tại; kiểm đơn vị quy đổi và kênh bán tham chiếu; không biến số tháng tồn thành cam kết ngày hết hàng.
- [ ] M20/C54/V40: nguồn đơn hàng đã có thì không phát cảnh báo cố định “chưa đồng bộ”; lấy năng lực từ tình trạng nguồn thực.
- [ ] M25/V26/V32: nhóm peer và cặp mua phải có định nghĩa, phạm vi và mẫu số rõ.

## 5. Lịch thực hiện theo ngày, giờ và đầu ra

Tính từ sáng thứ Sáu 11/09. Có 6 ngày làm việc thông thường trước Go-live: 11, 14, 15, 16, 17, 18/09. Không mặc định làm cuối tuần; ngày 19 là dự phòng có xác nhận, ngày 20 cần bố trí trực triển khai vì là Chủ nhật.

### Thứ Sáu 11/09 — khóa phạm vi, bảo toàn bản vá và sẵn sàng chạy

| Giờ | Công việc | Kiểm tra để đóng |
|---|---|---|
| 09:15–10:00 | Chốt 126 mã, rubric, phân công 63/63; đọc hết các dòng ghi khớp nhưng còn điều kiện, ưu tiên C11/M41. | Danh sách duy nhất, không trùng/thiếu; tỷ lệ ghi nhận và tỷ lệ xác nhận được tách. |
| 10:00–11:00 | Đăng + người sửa máy 24 đọc diff của stash đúng tên; so với `f692e45`; phân loại bản vá đã lên Git/còn thiếu/thử nghiệm. | Mọi thay đổi backend trong stash có kết luận. Chưa cần áp lại; bản cần giữ phải tích hợp có test. |
| 11:00–12:00 | Kiểm health, bản chạy thực, tài khoản/scope, quyền ETC, bất biến dữ liệu; kiểm quyền truy cập Bravo và độ mới từng bảng. | Mỗi phép có PASS/FAIL/CHƯA ĐỦ NGUỒN và bằng chứng; phép bị bỏ qua phải có lý do. |
| 13:00–14:30 | Hoàn thiện danh sách ưu tiên A/B, bắt đầu V03, M16, V11, C54; đọc bản vá hiện có trước khi viết lại. | Có test tái hiện lỗi hoặc bằng chứng bản hiện tại đã sửa; query đối chứng đúng tài khoản/kỳ. |
| 14:30–15:30 | DNH xác nhận nguồn thiếu và chính sách: CTKM, target SKU, công nợ lịch sử, thu tiền/cam kết, khóa hợp đồng, trạng thái chốt. | Câu hỏi nguồn có người nhận, hạn phản hồi 14/09 trước 10:00; không tự đánh dấu đạt. |
| 15:30–16:30 | Chuẩn bị runner chỉ chạy 126 mã giữ lại, lưu từng câu và resume; kiểm dừng theo ngân sách; chuẩn bị 3–5 tài khoản demo đúng vai. | Không chạy API tự động; không lưu mật khẩu vào Git; tài khoản demo chưa được gửi ra ngoài khi chưa duyệt. |
| 16:30–17:30 | Chốt chi phí cho phép, giờ tester rảnh, lịch deploy 14/09; bàn giao backlog và các bản vá nhỏ đã test. | Có người trực mỗi việc, có lệnh kiểm và bằng chứng để phiên sau tiếp tục. |

**Không bắt buộc chạy trả phí hôm nay.** Nếu còn ngân sách và không trùng lượt đồng nghiệp đang test, có thể chạy pilot nhỏ sau khi Đăng xác nhận; ghi riêng đây là pilot, không coi là vòng 126 đã hoàn tất.

### Thứ Hai 14/09 — chốt A/B và chạy vòng nền 126 câu

| Giờ | Công việc | Kiểm tra để đóng |
|---|---|---|
| 08:30–09:00 | Hợp nhất thay đổi cuối tuần nếu có; đọc phản hồi nguồn của DNH; kiểm không ai đang chạy eval khác. | Không còn nhánh sửa cùng file không rõ chủ; khóa bản ứng viên sáng. |
| 09:00–11:30 | Hoàn tất cụm A/B, bộ hồi quy bắt buộc và các bản vá trong stash cần giữ. | Test mục tiêu + toàn bộ backend; đối chứng thật cho số đã sửa; 0 lỗi Critical/High đã biết trên đường sắp chạy. |
| 11:30–12:00 | Deploy một lần, restart đúng dịch vụ, kiểm health/commit/sync và các cổng miễn phí. | Không chạy supervisor thủ công; rollback sẵn; công cụ không lỗi hoặc sai phạm vi. |
| 13:00–13:45 | Smoke ba vai, tổng 9 câu ưu tiên C02/C29/C54, M16/M20/M25, V03/V33/V39; pilot đo chi phí nếu chưa có. | Sai quyền/sai số nặng/cạn tool thì dừng vòng lớn; không dùng test xanh thay thế smoke. |
| 13:45–17:30 | Chạy vòng nền 126 câu, session riêng, lưu sau từng câu; chấm ngay khi có kết quả. | Khóa commit trong suốt lượt chạy. Tốc độ thực tế quyết định số hoàn thành; phần còn lại resume sáng 15/09, không tăng tải bừa. |

Trong lúc vòng chạy hoạt động chỉ sửa trên môi trường dev, chưa deploy. Reviewer ghi nguyên nhân chung thay vì tạo nhiều yêu cầu sửa trùng nhau.

### Thứ Ba 15/09 — chấm đủ vòng nền, sửa các cụm còn lại

| Giờ | Công việc | Kiểm tra để đóng |
|---|---|---|
| 08:30–10:00 | Resume vòng nền nếu còn; hai người chấm hoàn tất 126 câu; rà lại 72 câu từng ghi đạt. | 126/126 có kết quả vòng nền; không ô trống. Nguồn thiếu và lỗi thật tách riêng. |
| 10:00–12:00 | Sửa cụm C theo nguyên nhân chung, không theo thứ tự mã. | Kiểm khách duy nhất, lịch sử, nhóm âm/0, địa bàn và chuỗi cohort. |
| 13:00–15:00 | Sửa cụm D/E, hoàn thiện đối chứng các câu SQL sai trọng tâm. | Đủ SKU/khách/danh sách; kiểm NC/RO/DiscountRate/target thật; không tạo dữ liệu không có. |
| 15:00–16:30 | Hoàn thiện F và cách trả lời G/H/I sau xác nhận nguồn. | Đối chứng tồn kho thật; thiếu nguồn có bằng chứng và trả được phần hỗ trợ. |
| 16:30–17:30 | Review diff, test và chốt bản sửa chuẩn bị ngày 16. | Mỗi lỗi liên kết tới commit + test + câu cần retest; chưa tự chuyển sang đạt. |

Nếu 126 câu chưa chấm xong lúc 10:00: PMO cập nhật giờ hoàn thành dựa trên tốc độ thực đo, ưu tiên bổ sung người chấm; không tuyên bố đạt theo số câu đã chấm riêng.

### Thứ Tư 16/09 — retest theo ảnh hưởng và chốt ứng viên cuối

| Giờ | Công việc | Kiểm tra để đóng |
|---|---|---|
| 08:30–10:30 | Sửa lỗi còn lại, ưu tiên Critical/High và lỗi ảnh hưởng nhiều câu. | Số liệu sửa được đo lại trên Bravo/local đúng nguồn, không chỉ unit test. |
| 10:30–12:00 | Toàn bộ test; kiểm quyền âm tính; rà danh sách câu bị ảnh hưởng bởi từng hàm/prompt. | Có ma trận phạm vi retest. Không để test bắt lỗi bị deselect mà không giải thích. |
| 13:00–13:45 | Deploy gộp ứng viên cuối, cổng miễn phí + smoke. | Bản chạy xác định được commit; ngân sách retest đã kiểm. |
| 13:45–16:30 | Retest toàn bộ câu không đạt và các câu dùng chung đường vừa sửa. | Người chấm xác nhận độc lập kết quả chuyển đạt. Không giới hạn 20–30 câu nếu phạm vi ảnh hưởng lớn hơn. |
| 16:30–17:30 | Chốt bảng ứng viên gửi DNH nghiệm thu. | Mục tiêu 126/126; nếu dưới 120 hoặc còn lỗi Critical/High, báo đỏ tiến độ ngay. |

Nếu sửa prompt/router dùng chung ảnh hưởng toàn bộ câu: cần chạy lại toàn bộ 126 hoặc cung cấp phạm vi ảnh hưởng được review thuyết phục. Không viện lý do tiết kiệm API để bỏ kiểm chứng đường đã thay đổi.

### Thứ Năm 17/09 — nghiệm thu độc lập và hoàn thiện demo

- 08:30–10:00: DNH kiểm tài khoản, quyền và các câu giới hạn nguồn; kiểm 3–5 tài khoản demo theo biên bản họp.
- 10:00–12:00: xác nhận độc lập các câu vừa sửa, đối chiếu ít nhất 15 câu đạt rải đều C/M/V và các số tổng quan trọng.
- 13:00–15:00: UAT giao diện ba vai: đăng nhập, streaming, tải Excel, danh sách dài, câu hỏi tiếp nối, thông báo thiếu nguồn và quota. Số liệu hiển thị và Excel phải cùng kỳ/phạm vi.
- 15:00–16:00: rà thông tin sản phẩm chi tiết theo danh mục nguồn; tên/mã/quy cách/đơn vị tính không bị đổi nghĩa khi trả lời.
- 16:00–17:30: đóng biên bản 126 câu. Chốt mục đầy đủ dữ liệu và mục giới hạn nguồn riêng; mọi câu còn lại có chủ xử lý và giờ retest.

**Hạn chất lượng:** kết thúc ngày 17 phải có bằng chứng 126/126 đáp ứng rubric để giữ cam kết “đúng tất cả”. Nếu chưa đủ, không đổi mẫu số: trình rõ phương án khắc phục trước 18 hoặc đề nghị điều chỉnh phạm vi/lịch chính thức.

### Thứ Sáu 18/09 — khóa phát hành, chi phí, vận hành

- 08:30–10:00: chỉ sửa lỗi chặn nghiệm thu còn lại; không thêm tính năng. Bản nào đổi vẫn phải retest phạm vi ảnh hưởng.
- 10:00–12:00: diễn tập khôi phục và rollback trong phạm vi được duyệt; kiểm sao lưu auth/cấu hình/dữ liệu cần thiết, khả năng dịch vụ tự hồi phục và báo lỗi đồng bộ. Không làm gián đoạn tester bất ngờ.
- 13:00–14:30: chốt chi phí thực tế theo vai, lượt hỏi, cache, số tool và P50/P95; lập dự toán vận hành theo số người/lượt hỏi dự kiến, không lấy giá niêm yết thay chi phí thực đo.
- 14:30–15:30: bàn giao 3–5 tài khoản demo qua kênh an toàn sau phê duyệt; hướng dẫn phạm vi quyền, kỳ dữ liệu và cách phản hồi UAT.
- 15:30–16:30: kiểm tiến độ mốc Notify Outlook đang ghi triển khai trong biên bản. Nếu thuộc Go-live, phải có test gửi thử đúng người nhận và tiêu chí nghiệm thu; nếu tách đợt, PMO phải ghi quyết định, không ngầm bỏ.
- 16:30–17:30: họp Go/No-go; khóa commit, backup, runbook, số hotline/đầu mối, giờ deploy và ca trực Chủ nhật 20/09.

### Thứ Bảy 19/09 và Chủ nhật 20/09

- 19/09 chỉ là dự phòng đã thống nhất nhân sự: xử lý lỗi chặn, không thêm chức năng. Thay đổi phải tạo bản ứng viên mới và kiểm lại, không lén sửa máy 24.
- 20/09: triển khai đúng khung giờ được DNH duyệt; kiểm health, sync, quyền và smoke ba vai sau triển khai; theo dõi phiên đầu. Nếu rò quyền, sai số trọng yếu hoặc lỗi diện rộng, dừng mở rộng và rollback theo runbook.
- Nếu 18/09 chưa có phê duyệt/ca trực/ngân sách hoặc chất lượng chưa đạt, PMO phải thông báo ảnh hưởng mốc 20/09. Không tự mặc định có người làm Chủ nhật.

## 6. Cách ghi sheet và gói bằng chứng

Sheet đã thêm cột nên **dùng tên tiêu đề, không dùng cứng chữ E/I/J cũ**:

- `TÍnh cần thiết của câu hỏi`: phạm vi và lý do loại/giữ.
- `Kết quả chạy`: giữ nhận xét lần chạy gốc.
- `Đã sửa`: ngày sửa, commit, nội dung, đường dẫn bằng chứng; ghi rõ “chờ retest” nếu mới có code.
- `Chốt đánh giá`: kết quả sau kiểm chứng, ngày retest, vai/tài khoản, kỳ, người chấm và giới hạn nếu có.

Nếu kết quả mới phát hiện sai thì nó thay thế chốt đạt cũ trong báo cáo hiện tại; không cộng đạt chỉ vì một cột cũ từng ghi khớp. Không ghi đè góp ý ban đầu của tester.

Mẫu một bản ghi: `M16 | ĐẠT — đầy đủ dữ liệu | retest dd/mm hh:mm | commit ... | vai miền MB | kỳ ... | đủ N/N nhân viên | SQL ... | người chấm ...`.

Mỗi câu lưu: ID, câu hỏi chính xác, tài khoản/role/scope, kỳ, commit triển khai, thời điểm sync, tool/args không chứa bí mật, câu trả lời, kết quả đối chứng, chênh lệch, trạng thái và reviewer. Không lưu mật khẩu/API key trong output hoặc Git.

## 7. Nguồn đối chứng và thứ tự kiểm tiết kiệm chi phí

1. Đọc câu hỏi + nhận xét + câu trả lời đã có, xác định đúng kỳ/role; tận dụng kết quả còn phù hợp trước khi gọi API lại.
2. Chạy trực tiếp hàm báo cáo trên warehouse local để tìm lỗi logic, không gọi model.
3. Đối chiếu Bravo bằng truy vấn chỉ đọc, đúng scope và mốc đồng bộ; đối với nguồn chỉ có trong warehouse, ghi rõ đây là đối chứng warehouse, không gọi là đã check Bravo.
4. Chạy test mục tiêu và bộ bất biến. Tổng khớp phải kèm kiểm danh sách/khóa để bắt trường hợp cả hai vế cùng mất người.
5. Sau deploy mới hỏi chatbot đúng tài khoản; lưu trả lời thật để reviewer chốt.

Các cổng đã có trong repo cần dùng và lưu output: `kiem_tai_khoan_thieu_pham_vi.py`, `verify_etc_channel_scope.py`, `doi_chieu_so_lieu_tool_moi.py`, `kiem_dinh_tuyen_138.py`, test backend. Xem cách gọi/tham số của phiên bản hiện tại trước khi chạy; một cổng bị bỏ qua không được coi là đạt.

Các mapping cần đọc lại trước khi dùng checker: M22/S88, C28/S91, M24/S92, M25/S89, S26 nguồn local. Bảng SQL cũ có thể khác logic chuẩn hiện tại; chỉ sửa đối chứng khi có bằng chứng độc lập, không để chatbot và checker cùng hợp thức hóa sai số.

## 8. API, tài khoản và giới hạn vận hành

- Ngân sách $15 trong kế hoạch 08–09/09 là ngân sách đợt cũ, không tự gia hạn cho đợt này. Đăng xác nhận số dư và trần chi mới trước pilot/vòng lớn.
- Chạy pilot nhỏ đủ ba vai; đo chi phí thực gồm cache write/read, output và vòng tool. Dự toán = chi phí pilot theo từng vai × số câu còn cần chạy + phần dự phòng retest được duyệt.
- Khối lượng tham chiếu: một vòng 126 + 9 smoke + 20–40 retest = 155–175 lượt, chưa tính demo/phát sinh. Nếu phải chạy lại toàn bộ sau sửa prompt chung thì cộng thêm 126 lượt; không hứa trần tiền khi chưa đo.
- Runner có chế độ `--only` và `--resume`; truyền đúng danh sách 126 mã. Cần kiểm/hoàn thiện cơ chế giới hạn chi phí và dừng an toàn trước khi chạy, không giả định có sẵn tham số budget. Lưu kết quả ngay sau từng câu.
- Một người điều phối lượt test. Không chạy business-eval nền hoặc tác vụ SYSTEM đồng thời với tester. Tắt/kiểm lịch không đồng nghĩa tiến trình đang chạy đã dừng: phải kiểm riêng tiến trình thực.
- Tài khoản QLV đối chứng đã yêu cầu: `thuy.nguyen`, Nguyễn Thị Hồng Thúy, TM25010183, MB; xác nhận lại trong auth thật trước test. Không nhầm với Nguyễn Thị Thanh Thủy, vai Giám đốc miền/kênh.
- Ba tài khoản demo cốt lõi: C-Level, giám đốc miền MB, QLV MB. Hai tài khoản tùy chọn: kênh ETC và vùng khác, theo phạm vi DNH duyệt. Kiểm cả câu hỏi cố truy xuất ngoài phạm vi; không cấp quyền rộng để thuận tiện test.
- Đo P50/P95 theo log thật và tỷ lệ timeout. Ngưỡng nghiệm thu tốc độ phải chốt với DNH sau pilot; không tự đặt rồi trình như cam kết đã duyệt.

## 9. Cổng quyết định cuối và xử lý trễ

- [ ] 126/126 câu có đánh giá trên bằng chứng phù hợp bản cuối; không còn “chưa check”.
- [ ] 126/126 đáp ứng rubric để công bố “đúng tất cả câu trong phạm vi”; tách câu đáp ứng bằng dữ liệu và câu giới hạn nguồn được chấp thuận.
- [ ] 0 lỗi Critical/High; 0 rò quyền; không có phép tính trọng yếu chưa đối chứng.
- [ ] Các câu bị loại được công bố riêng, không tính vào tử/mẫu; mẫu số và lý do đã được duyệt.
- [ ] Bản chạy thực, thời điểm sync, test tự động, SQL đối chứng và log chatbot có thể truy vết.
- [ ] 3–5 tài khoản demo được kiểm; không bí mật trong Git; ngân sách/đầu mối thanh toán API được xác nhận.
- [ ] Có backup, rollback, người trực ngày 20 và quyết định Go-live.

Nếu 120–125/126: có thể báo trung thực đã vượt 95%, nhưng chưa đạt mục tiêu tất cả. Chỉ PMO/DNH được quyết định chấp nhận ngoại lệ phát hành; danh sách còn lại, ảnh hưởng và hạn sửa phải công khai. Dưới 120 hoặc có Critical/High: báo không đạt cổng, không tự giảm mẫu số.

Rủi ro và phương án:

| Rủi ro | Thời điểm phải biết | Cách xử lý |
|---|---|---|
| Mất bản vá trong stash | 11/09 trước trưa | Review diff, tích hợp có test; giữ backup, không pop mù. |
| Bravo/VPN hoặc sync lỗi | 11/09, mỗi lần đối chứng | Làm test/local trước; ghi nguồn chưa xác minh, không chốt số dựa vào kho cũ. |
| DNH chưa trả lời nguồn | 14/09 10:00 | PMO thúc đầu mối; trả đúng giới hạn đã chứng minh, phần chưa xác nhận giữ chờ kiểm. |
| Tester không đủ năng lực chấm 126 câu | Đo từ pilot/vòng nền | Bổ sung reviewer hoặc kéo dài khung được duyệt; không tự dùng model làm người nghiệm thu cuối. |
| Hết tiền/quota | Trước vòng lớn và từng batch | Dừng trả phí, lưu resume; tiếp tục kiểm miễn phí; xin ngân sách rõ ràng, không né hạn mức. |
| Sửa prompt chung muộn | Hạn ứng viên 16/09 | Tính lại phạm vi retest và chi phí; báo ảnh hưởng lịch ngay. |
| Không có ca trực cuối tuần | 18/09 trước Go/No-go | DNH/PMO chốt ca trực hoặc điều chỉnh lịch có thông báo. |

## 10. Sau Go-live đến đóng dự án 30/09

- 21–24/09: theo dõi lỗi thật theo vai, sai số, timeout, sync và chi phí; xử lý sự cố theo mức độ, không tự chạy lại eval trả phí hàng ngày.
- 25–29/09: đóng lỗi phát sinh, kiểm hồi quy, bàn giao runbook/quyền vận hành/nguồn dữ liệu và các giới hạn đã ký nhận; chốt phạm vi Notify Outlook theo quyết định đã ghi.
- 30/09: nghiệm thu đóng dự án với tỷ lệ thực tế, chi phí vận hành thực, danh sách tồn đọng nếu còn và người chịu trách nhiệm. Không ghi hoàn thành nếu vẫn có đầu việc bắt buộc chưa được nghiệm thu.

### Việc bắt đầu ngay sau khi duyệt kế hoạch

1. Đăng xác nhận người chấm A/B, trần ngân sách đợt này và giờ đồng nghiệp đang test để không chạy chồng.
2. Review stash máy 24 và khóa baseline triển khai.
3. Kiểm miễn phí; xử lý A/B trước, đồng thời gửi danh sách cần DNH xác nhận nguồn.
4. Tạo sổ bằng chứng cho đủ 126 câu; ưu tiên retest bản đã sửa trước khi viết lại.

Tài liệu này chưa thực hiện deploy, chưa tạo tài khoản, chưa gửi yêu cầu cho DNH, chưa chạy API và chưa thay đổi kết quả trên sheet.
