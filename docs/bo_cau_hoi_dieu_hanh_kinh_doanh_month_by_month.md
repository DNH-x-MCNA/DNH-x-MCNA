# Bộ câu hỏi điều hành kinh doanh month-by-month — Dược Nam Hà

> SQL đối soát cho từng mã câu hỏi: xem
> [Catalog SQL check](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md).

## 1. Kết luận sau khi rà bộ câu hỏi hiện có

Bộ `scripts/business_stress_suite.py` hiện có 90 câu, bao phủ khá tốt việc kiểm tra số liệu tại
một kỳ cụ thể: doanh thu, đội ngũ, khách hàng/sản phẩm, công nợ, KPI, lương thưởng, khuyến mãi,
tồn kho và chất lượng dữ liệu. Bộ này phù hợp làm **business stress suite**, nhưng **chưa đủ làm
bộ câu hỏi điều hành tháng cho Ban lãnh đạo** vì còn các khoảng trống chính:

1. Phần lớn câu hỏi đang cố định ở tháng 7/2026 hoặc một snapshot, chưa được chuẩn hóa thành chuỗi
   12–24 tháng, MoM, YoY, lũy kế năm và so kế hoạch.
2. Chưa có “growth bridge” để giải thích tăng/giảm đến từ kênh, miền, vùng, khách hàng, sản phẩm,
   giá, sản lượng hay cơ cấu.
3. Thiếu câu hỏi về chất lượng tăng trưởng: doanh thu thuần, biên lợi nhuận, chiết khấu, hàng trả,
   mức độ tập trung, tăng trưởng trên cùng tập khách hàng.
4. Thiếu vòng đời khách hàng: mở mới, mua lại, tái kích hoạt, ngừng mua, cohort và tần suất mua.
5. Thiếu độ phủ sản phẩm/địa bàn, năng suất tuyến bán hàng và cơ hội bán chéo.
6. Công nợ hiện mạnh ở snapshot nhưng thiếu lịch sử thu tiền, DSO và dịch chuyển nhóm tuổi nợ qua
   từng tháng.
7. Tồn kho mới ở mức tổng quan; thiếu stock-out, hàng chậm luân chuyển, cận date, mất doanh số do
   thiếu hàng và cân đối cung–cầu.
8. Chưa có nhóm điều hành riêng cho ETC: kế hoạch thầu, tỷ lệ trúng, thực hiện hợp đồng, giá trị còn
   lại và rủi ro hết hạn.
9. Thiếu dự báo cuối tháng/cuối quý, gap-to-target, cảnh báo sớm và danh sách hành động có chủ sở hữu.
10. Chưa tách rõ câu hỏi theo cấp C-level, TP/Giám đốc miền/Giám đốc kênh và Quản lý vùng.

Vì vậy: **không nên bỏ bộ 90 câu hiện tại**. Hãy dùng bộ đó để kiểm thử số liệu; dùng master list
dưới đây làm backlog nghiệp vụ và menu câu hỏi điều hành.

## 2. Chuẩn chung cho mọi câu trả lời

Trừ khi người hỏi chỉ định khác, “theo tháng” phải trả tối thiểu 12 tháng gần nhất và có:

- Tháng hiện tại/MTD, tháng đã chốt gần nhất và lũy kế YTD.
- Thực hiện, kế hoạch, % hoàn thành, chênh lệch tuyệt đối và chênh lệch phần trăm.
- MoM và YoY; nếu chưa đủ lịch sử phải nói rõ thiếu kỳ nào.
- Tỷ trọng đóng góp và mức đóng góp vào tăng/giảm chung, không chỉ xếp hạng.
- Drill-down theo chuỗi: Toàn quốc → kênh → miền → vùng → nhân viên → khách hàng → sản phẩm → hóa đơn.
- Mốc dữ liệu, nguồn dữ liệu và cảnh báo chất lượng dữ liệu.
- Top nguyên nhân, ngoại lệ cần xử lý và gợi ý hành động; không biến tương quan thành kết luận nguyên nhân.

Các chiều lọc chuẩn: kỳ tháng, OTC/ETC, miền, vùng, tỉnh, chi nhánh/NPP, TP/Giám đốc, QLV,
TDV/nhân viên, nhóm khách hàng, khách hàng, nhóm sản phẩm, SKU, chương trình khuyến mãi và trạng
thái đơn/hóa đơn.

## 3. Câu hỏi của C-level / Tổng Giám đốc / Giám đốc Kinh doanh toàn quốc

### A. Scorecard tăng trưởng toàn công ty

1. **C01** — Doanh thu thuần từng tháng 24 tháng gần nhất của toàn công ty, OTC và ETC là bao nhiêu; MoM, YoY và CAGR/nhịp tăng trưởng thế nào? — [SQL: S01](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
2. **C02** — Mỗi tháng đạt bao nhiêu phần trăm kế hoạch; thiếu/vượt bao nhiêu tiền theo toàn công ty, kênh và miền? — [SQL: S02](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
3. **C03** — Lũy kế YTD thực hiện so kế hoạch và cùng kỳ năm trước thế nào; cần bình quân bao nhiêu mỗi tháng còn lại để đạt kế hoạch năm? — [SQL: S79](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
4. **C04** — Run-rate tháng hiện tại đang hướng tới mức nào; kênh/miền nào tạo rủi ro hụt kế hoạch cuối tháng? — [SQL: S03](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
5. **C05** — Tăng/giảm doanh thu tháng này so tháng trước và cùng kỳ đến từ kênh, miền, vùng nào; mỗi đơn vị đóng góp bao nhiêu vào biến động chung? — [SQL: S04](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
6. **C06** — Biến động doanh thu được giải thích bao nhiêu bởi số đơn, số khách mua, tần suất mua, sản lượng, giá bán và cơ cấu sản phẩm? — [SQL: S05](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
7. **C07** — Trung bình trượt 3 tháng và 6 tháng đang tăng hay giảm; có điểm gãy xu hướng ở tháng nào? — [SQL: S06](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
8. **C08** — Những tháng có tính mùa vụ cao/thấp nhất theo kênh và nhóm sản phẩm là tháng nào; tháng hiện tại lệch mô hình mùa vụ bao nhiêu? — [SQL: S80](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
9. **C09** — Giá trị đơn hàng bình quân, số đơn và doanh thu/khách hoạt động thay đổi month-by-month ra sao? — [SQL: S07](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
10. **C10** — Tỷ trọng OTC/ETC thay đổi thế nào qua từng tháng; sự thay đổi cơ cấu làm tăng hay giảm tốc độ tăng trưởng chung? — [SQL: S08](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
11. **C11** — Doanh thu đang phụ thuộc vào top 10 khách hàng, top 10 sản phẩm và top 3 miền/vùng ở mức nào; xu hướng tập trung tăng hay giảm? — [SQL: S70](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
12. **C12** — Nếu loại các giao dịch bất thường, đơn lớn đột biến, trả hàng và điều chỉnh, tăng trưởng cốt lõi từng tháng còn bao nhiêu? — [SQL: S09](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### B. Chất lượng doanh thu và lợi nhuận

13. **C13** — Doanh thu gộp, chiết khấu, khuyến mãi, hàng trả và doanh thu thuần từng tháng là bao nhiêu? — [SQL: S87](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
14. **C14** — Lợi nhuận gộp và biên lợi nhuận gộp theo tháng, kênh, miền và nhóm sản phẩm thay đổi thế nào? — [SQL: S10](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
15. **C15** — Kênh/miền/sản phẩm nào tăng doanh thu nhưng giảm biên lợi nhuận; nguyên nhân do giá, chiết khấu, giá vốn hay cơ cấu? — [SQL: S10](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
16. **C16** — Giá bán thực tế bình quân của từng SKU thay đổi MoM/YoY ra sao; SKU nào có dấu hiệu giảm giá hoặc xói mòn giá? — [SQL: S11](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
17. **C17** — Tỷ lệ hàng trả/điều chỉnh trên doanh thu theo tháng và kênh là bao nhiêu; nơi nào vượt ngưỡng? — [SQL: S77](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
18. **C18** — Chi phí khuyến mãi/chiết khấu tạo thêm bao nhiêu doanh thu và lợi nhuận; chương trình nào thực sự có uplift so baseline? — [SQL: S12](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
19. **C19** — Sản phẩm/khách hàng nào doanh thu cao nhưng lợi nhuận thấp hoặc âm; tỷ trọng của nhóm này tăng hay giảm? — [SQL: S10](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
20. **C20** — Tăng trưởng trên cùng tập khách hàng và cùng tập sản phẩm (like-for-like) là bao nhiêu, tách khỏi tăng trưởng do mở mới? — [SQL: S13](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### C. Kênh, miền, địa bàn và hệ thống phân phối

21. **C21** — Xếp hạng kênh, miền, vùng, tỉnh và chi nhánh/NPP theo doanh thu, tăng trưởng, % kế hoạch và đóng góp tăng trưởng từng tháng. — [SQL: S14](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
22. **C22** — Đơn vị nào tăng trưởng liên tục 3/6 tháng; đơn vị nào giảm liên tục 3/6 tháng? — [SQL: S49](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
23. **C23** — Địa bàn nào có quy mô lớn nhưng tăng trưởng thấp; địa bàn nào quy mô nhỏ nhưng đang tăng nhanh? — [SQL: S50](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
24. **C24** — Tỉnh/vùng nào có độ phủ khách hàng thấp so với các địa bàn tương đồng; cơ hội trắng nằm ở đâu? — [SQL: S51](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
25. **C25** — Năng suất mỗi NPP/chi nhánh theo tháng là bao nhiêu; NPP nào doanh thu giảm, tồn kho tăng hoặc công nợ xấu đi? — [SQL: S15](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
26. **C26** — Khách mua đồng thời OTC và ETC đóng góp bao nhiêu doanh thu/công nợ; xu hướng mua chéo kênh ra sao? — [SQL: S16](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
27. **C27** — Có sự dịch chuyển doanh thu bất thường giữa kênh, miền, chi nhánh hoặc mã nhân viên qua các tháng không? — [SQL: S17](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
28. **C28** — Nếu loại ảnh hưởng của thay đổi địa bàn, chuyển nhân viên và chuyển khách, tăng trưởng thực của từng đơn vị còn bao nhiêu? — [SQL: S91](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### D. Khách hàng và danh mục sản phẩm

29. **C29** — Số khách hoạt động, khách mới, khách mua lại, khách tái kích hoạt và khách ngừng mua từng tháng là bao nhiêu? — [SQL: S18](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
30. **C30** — Tỷ lệ giữ chân khách theo cohort tháng mở mới sau 1/3/6/12 tháng là bao nhiêu, theo kênh và miền? — [SQL: S19](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
31. **C31** — Doanh thu mất đi từ khách ngừng mua và doanh thu tăng thêm từ khách mới/tái kích hoạt bù được bao nhiêu? — [SQL: S90](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
32. **C32** — Top khách hàng tăng/giảm mạnh nhất từng tháng là ai; thay đổi đó ảnh hưởng bao nhiêu đến toàn công ty? — [SQL: S71](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
33. **C33** — Nhóm sản phẩm/SKU nào là động lực tăng trưởng, nhóm nào kéo giảm tăng trưởng và nhóm nào mất thị phần nội bộ? — [SQL: S21](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
34. **C34** — Doanh thu sản phẩm mới sau 1/3/6/12 tháng ra mắt đạt bao nhiêu so kế hoạch; độ phủ khách hàng ra sao? — [SQL: S22](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
35. **C35** — Mức độ phụ thuộc vào sản phẩm chủ lực qua từng tháng; nếu top 1/top 5 giảm 20% thì doanh thu bị ảnh hưởng bao nhiêu? — [SQL: S23](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
36. **C36** — SKU nào có độ phủ khách hàng tăng nhưng doanh thu/khách giảm, hoặc doanh thu tăng nhưng độ phủ co lại? — [SQL: S73](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### E. Công nợ, tồn kho, ETC và rủi ro thực thi

37. **C37** — Dư nợ, nợ quá hạn, tỷ lệ quá hạn và cơ cấu tuổi nợ month-by-month theo kênh/miền thay đổi thế nào? — [SQL: S25](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
38. **C38** — Thu tiền trong tháng so với doanh thu và kế hoạch thu tiền là bao nhiêu; DSO và vòng quay công nợ thay đổi ra sao? — [SQL: S45](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
39. **C39** — Khách nào đồng thời doanh thu giảm, nợ quá hạn tăng và tuổi nợ xấu đi qua 2–3 tháng? — [SQL: S26](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
40. **C40** — Top khách nợ chiếm bao nhiêu phần trăm tổng nợ; rủi ro tập trung công nợ tăng hay giảm? — [SQL: S24](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
41. **C41** — Giá trị tồn kho, số tháng tồn, hàng chậm luân chuyển, stock-out và hàng cận date thay đổi thế nào theo tháng? — [SQL: S27](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
42. **C42** — SKU nào mất doanh số do thiếu hàng; SKU nào tồn cao trong khi doanh số giảm liên tục? — [SQL: S47](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
43. **C43** — Kế hoạch thầu ETC, giá trị tham gia, giá trị trúng, tỷ lệ trúng và doanh thu thực hiện theo tháng/quý là bao nhiêu? — [SQL: S29](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
44. **C44** — Hợp đồng ETC nào thực hiện chậm, còn giá trị lớn chưa giải ngân, sắp hết hạn hoặc phát sinh công nợ quá hạn? — [SQL: S86](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### F. Tổ chức bán hàng, dự báo và điều hành

45. **C45** — Tỷ lệ nhân sự đạt 65/70%, 80%, 100% và 120% KPI từng tháng theo kênh/miền/chức danh là bao nhiêu? — [SQL: S30](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
46. **C46** — Năng suất doanh thu trên đầu người và trên quản lý thay đổi thế nào; đơn vị nào tăng headcount nhưng năng suất giảm? — [SQL: S32](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
47. **C47** — Cá nhân/đội nào dưới 80% liên tiếp 3 tháng hoặc biến động mạnh; khoảng hụt doanh thu là bao nhiêu? — [SQL: S64](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
48. **C48** — Chi phí thưởng kinh doanh trên doanh thu/lợi nhuận theo tháng là bao nhiêu; cơ chế thưởng có tương quan với tăng trưởng bền vững không? — [SQL: S33](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
49. **C49** — Độ phủ tuyến, số lượt viếng thăm, tỷ lệ viếng thăm có đơn và doanh thu/lượt viếng thăm thay đổi ra sao? — [SQL: S34](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
50. **C50** — Dự báo doanh thu cuối tháng/quý theo kênh/miền là bao nhiêu; khoảng tin cậy và giả định chính là gì? — [SQL: S35](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
51. **C51** — Ba rủi ro lớn nhất khiến không đạt kế hoạch là gì; mỗi rủi ro ảnh hưởng ước tính bao nhiêu tiền? — [SQL: S82](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
52. **C52** — Mỗi kênh/miền cam kết hành động gì để đóng gap; chủ sở hữu, hạn hoàn thành và kết quả tháng sau ra sao? — [SQL: S36](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
53. **C53** — Số liệu doanh thu, KPI, công nợ, tồn kho, khuyến mãi và lương đang chốt đến tháng/ngày nào; nguồn nào chưa đồng bộ? — [SQL: S37](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
54. **C54** — Chỉ tiêu nào có dấu hiệu sai do trùng tầng quản lý, thiếu mapping, thay đổi mã, thiếu target hoặc snapshot chưa chốt? — [SQL: S38](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

## 4. Câu hỏi của TP / Giám đốc miền / Giám đốc kênh

### A. Điều hành kết quả miền/kênh

1. **M01** — Doanh thu từng tháng của miền/kênh tôi so kế hoạch, tháng trước, cùng kỳ và YTD thế nào? — [SQL: S01](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
2. **M02** — Gap tới kế hoạch tháng/quý còn bao nhiêu; mỗi vùng cần đóng góp thêm bao nhiêu? — [SQL: S43](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
3. **M03** — Vùng nào đóng góp nhiều nhất vào tăng/giảm của miền/kênh tháng này? — [SQL: S04](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
4. **M04** — Xếp hạng các vùng theo doanh thu, tăng trưởng, % kế hoạch, lợi nhuận và công nợ; thứ hạng thay đổi ra sao 6 tháng qua? — [SQL: S14](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
5. **M05** — Vùng nào dưới 80% kế hoạch liên tiếp; tổng hụt doanh thu tích lũy là bao nhiêu? — [SQL: S58](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
6. **M06** — Doanh thu ngày/tuần trong tháng đang chạy nhanh hay chậm hơn nhịp cần thiết để đạt target? — [SQL: S03](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
7. **M07** — Số khách mua, số đơn, AOV và tần suất mua của miền/kênh thay đổi thế nào qua từng tháng? — [SQL: S07](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
8. **M08** — Tăng trưởng hiện tại đến từ mở mới khách hàng hay tăng mua trên khách hàng hiện hữu? — [SQL: S90](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
9. **M09** — Đơn hàng/hóa đơn bất thường nào làm biến động kết quả tháng; nếu loại chúng thì kết quả còn bao nhiêu? — [SQL: S09](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
10. **M10** — Tỉnh/chi nhánh/NPP nào đang kéo giảm kết quả và cần ưu tiên can thiệp? — [SQL: S52](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### B. Quản trị vùng và đội ngũ

11. **M11** — Doanh số, target và % hoàn thành của từng QLV/đội theo tháng; ai cải thiện hoặc suy giảm mạnh nhất? — [SQL: S39](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
12. **M12** — Đội nào đạt 100%, 80%, qua cổng 65/70% hoặc dưới cổng; xu hướng 3 tháng thế nào? — [SQL: S31](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
13. **M13** — QLV nào có nhiều nhân viên dưới 80% nhất; phần hụt của đội tập trung ở ai? — [SQL: S65](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
14. **M14** — Đội nào có doanh thu cao nhưng phụ thuộc vào ít nhân viên hoặc ít khách hàng? — [SQL: S54](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
15. **M15** — Năng suất doanh thu/TDV, doanh thu/khách và doanh thu/ngày làm việc của từng đội thay đổi thế nào? — [SQL: S32](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
16. **M16** — Nhân viên nào giảm doanh số liên tiếp 3 tháng; giảm do mất khách, giảm tần suất hay giảm giá trị đơn? — [SQL: S55](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
17. **M17** — Nhân viên mới đạt ramp-up thế nào sau 1/2/3/6 tháng so với chuẩn cùng vai trò? — [SQL: S85](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
18. **M18** — Địa bàn trống, nhân viên nghỉ/chuyển vùng hoặc khách chưa gán người phụ trách ảnh hưởng bao nhiêu doanh thu? — [SQL: S81](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
19. **M19** — QLV nào có span of control quá lớn/nhỏ; quy mô đội có ảnh hưởng đến năng suất không? — [SQL: S66](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
20. **M20** — Thưởng/KPI của đội có khớp doanh số và chính sách đã chốt; có bất thường nào cần kiểm tra? — [SQL: S33](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### C. Khách hàng và địa bàn

21. **M21** — Top khách hàng theo doanh thu từng tháng; khách nào tăng/giảm mạnh và QLV nào phụ trách? — [SQL: S20](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
22. **M22** — Khách lớn nào ngừng mua, giảm mua hoặc kéo dài chu kỳ mua so với lịch sử? — [SQL: S88](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
23. **M23** — Số khách mới, tái kích hoạt, mua lại và ngừng mua của từng vùng; tỷ lệ giữ chân sau 3/6 tháng? — [SQL: S67](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
24. **M24** — Vùng nào mở nhiều khách mới nhưng doanh thu/khách và tỷ lệ mua lại thấp? — [SQL: S92](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
25. **M25** — Khách nào có tiềm năng bán chéo nhóm sản phẩm do đang mua ít SKU hơn nhóm khách tương đồng? — [SQL: S89](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
26. **M26** — Khách hàng nào có share-of-wallet nội bộ thấp: doanh thu lớn nhưng chỉ mua một nhóm sản phẩm? — [SQL: S89](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
27. **M27** — Tỉnh/huyện nào có ít khách hoạt động, ít đơn hoặc doanh thu/khách thấp hơn chuẩn miền? — [SQL: S53](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
28. **M28** — Tỷ lệ khách không gán TDV, sai vùng hoặc thiếu thông tin DMS theo tháng là bao nhiêu? — [SQL: S38](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
29. **M29** — NPP/chi nhánh nào có tăng trưởng khách hàng tốt nhưng công nợ hoặc tồn kho xấu đi? — [SQL: S15](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
30. **M30** — Danh sách 20 khách hàng ưu tiên cần giữ, thu hồi, tái kích hoạt hoặc mở rộng trong tháng tới là ai? — [SQL: S48](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### D. Sản phẩm, giá, khuyến mãi, công nợ và tồn kho

31. **M31** — Nhóm sản phẩm/SKU nào đóng góp nhiều nhất vào tăng/giảm của miền/kênh theo tháng? — [SQL: S21](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
32. **M32** — SKU chiến lược đạt bao nhiêu % target tại từng vùng; vùng nào có khoảng trống độ phủ lớn nhất? — [SQL: S46](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
33. **M33** — SKU nào doanh thu giảm do ít khách mua, ít đơn, giảm lượng/đơn hay giảm giá bán? — [SQL: S72](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
34. **M34** — Sản phẩm mới đạt độ phủ và doanh thu sau 1/3/6 tháng thế nào tại từng vùng? — [SQL: S22](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
35. **M35** — Chương trình khuyến mãi nào có nhiều khách tham gia nhưng không tạo tăng trưởng; chương trình nào tạo uplift tốt? — [SQL: S12](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
36. **M36** — Tỷ lệ trả hàng, chiết khấu và hàng tặng trên doanh thu của từng vùng thay đổi ra sao? — [SQL: S78](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
37. **M37** — Tổng nợ, nợ quá hạn, DSO và thu tiền của từng vùng/QLV qua từng tháng; đơn vị nào xấu đi nhanh nhất? — [SQL: S25](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
38. **M38** — Khách nào cần dừng/bóp bán vì nợ xấu; doanh thu có nguy cơ ảnh hưởng là bao nhiêu? — [SQL: S26](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
39. **M39** — SKU nào thiếu hàng ở miền/kênh và làm mất doanh số; SKU nào tồn cao hơn nhu cầu 3–6 tháng? — [SQL: S47](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
40. **M40** — Hàng cận date/chậm luân chuyển nào cần chuyển vùng, đẩy bán hoặc dừng nhập? — [SQL: S28](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### E. ETC, dự báo và hành động

41. **M41** — Với ETC, kế hoạch thầu, tỷ lệ trúng, doanh thu thực hiện và thu tiền từng tháng của từng vùng/khách hàng thế nào? — [SQL: S29](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
42. **M42** — Hợp đồng/gói thầu nào có tỷ lệ thực hiện thấp, còn giá trị lớn hoặc sắp hết hiệu lực? — [SQL: S86](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
43. **M43** — Dự báo cuối tháng của từng vùng/QLV là bao nhiêu; vùng nào có xác suất không đạt cao nhất? — [SQL: S35](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
44. **M44** — Với từng vùng dưới kế hoạch: ba nguyên nhân định lượng, ba hành động, người chịu trách nhiệm và deadline là gì? — [SQL: S36](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

## 5. Câu hỏi của Quản lý vùng

### A. Bám chỉ tiêu đội theo tháng

1. **V01** — Đội tôi đạt bao nhiêu doanh số và bao nhiêu % target tháng; MoM, YoY và YTD thế nào? — [SQL: S43](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
2. **V02** — Còn thiếu bao nhiêu để đạt 65/70%, 80%, 100% và 120%; mỗi ngày còn lại cần bán bao nhiêu? — [SQL: S59](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
3. **V03** — Doanh số từng ngày/tuần đang cao hay thấp hơn nhịp cần thiết; ngày nào không có phát sinh? — [SQL: S03](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
4. **V04** — Nhân viên nào đóng góp nhiều nhất vào tăng/giảm doanh số đội tháng này? — [SQL: S57](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
5. **V05** — Nếu loại đơn hàng lớn bất thường và hàng trả, kết quả thực chất của đội là bao nhiêu? — [SQL: S09](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
6. **V06** — Doanh thu đội đến từ bao nhiêu khách, bao nhiêu đơn; AOV và tần suất mua thay đổi thế nào? — [SQL: S07](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
7. **V07** — So với 3 tháng gần nhất, tháng này đội giảm ở số khách, số đơn, sản lượng hay giá trị đơn? — [SQL: S05](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
8. **V08** — Tỉnh/địa bàn con nào đang dưới kế hoạch; phần hụt là bao nhiêu và TDV nào phụ trách? — [SQL: S60](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
9. **V09** — Dự báo cuối tháng của đội theo run-rate hiện tại; kịch bản cơ sở/tốt/xấu là bao nhiêu? — [SQL: S35](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
10. **V10** — Hôm nay/tuần này cần ưu tiên khách hàng, sản phẩm và nhân viên nào để đóng gap lớn nhất? — [SQL: S84](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### B. Quản trị từng nhân viên

11. **V11** — Doanh số, target và % hoàn thành từng TDV theo tháng; xếp hạng và xu hướng 3/6 tháng? — [SQL: S56](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
12. **V12** — Ai dưới 65/70%, dưới 80%, đạt 100% hoặc vượt 120%; mỗi người còn thiếu bao nhiêu tiền? — [SQL: S31](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
13. **V13** — Ai giảm liên tiếp 2–3 tháng; nguyên nhân nằm ở khách mất, ít đơn, ít SKU hay giá trị đơn giảm? — [SQL: S55](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
14. **V14** — Ai có nhiều khách phụ trách nhưng tỷ lệ khách mua thấp; ai có ít khách nhưng doanh thu/khách cao? — [SQL: S44](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
15. **V15** — Ai mở nhiều khách mới nhưng tỷ lệ mua lại thấp; ai tái kích hoạt khách tốt nhất? — [SQL: S61](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
16. **V16** — Ai có ngày làm việc/đi tuyến nhưng không phát sinh đơn; tỷ lệ viếng thăm có đơn là bao nhiêu? — [SQL: S34](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
17. **V17** — Nhân viên nào có doanh số nhưng thiếu target, thiếu manager, sai địa bàn hoặc trùng mã? — [SQL: S38](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
18. **V18** — Thưởng và phụ cấp từng người thay đổi thế nào; có điểm nào không khớp KPI/chính sách? — [SQL: S33](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### C. Quản trị khách hàng và độ phủ

19. **V19** — Top khách hàng đội tôi từng tháng là ai; khách nào tăng/giảm mạnh nhất? — [SQL: S20](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
20. **V20** — Khách đã mua tháng trước nhưng chưa mua tháng này là ai; doanh thu có nguy cơ mất bao nhiêu? — [SQL: S40](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
21. **V21** — Khách im lặng 30/60/90 ngày là ai; lần mua gần nhất, giá trị và sản phẩm thường mua là gì? — [SQL: S69](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
22. **V22** — Khách mới tháng này là ai; đã có đơn lặp lại chưa và TDV nào phụ trách? — [SQL: S18](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
23. **V23** — Khách mua lại/tái kích hoạt là ai; doanh thu phục hồi so trước khi ngừng mua thế nào? — [SQL: S68](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
24. **V24** — Khách nào giảm tần suất mua, AOV hoặc số SKU/đơn so với 3 tháng trước? — [SQL: S62](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
25. **V25** — Khách nào chỉ mua một nhóm sản phẩm và có cơ hội bán chéo rõ nhất? — [SQL: S41](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
26. **V26** — Khách nào mua ít hơn các khách tương đồng cùng tỉnh/phân khúc? — [SQL: S63](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
27. **V27** — Khách nào chưa gán TDV, sai mã, sai tỉnh/vùng hoặc không có tên trong DMS? — [SQL: S75](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
28. **V28** — Danh sách khách ưu tiên tuần này theo bốn mục tiêu: giữ khách lớn, tái kích hoạt, thu nợ và bán chéo? — [SQL: S83](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

### D. Sản phẩm, đơn hàng, công nợ và tồn kho

29. **V29** — Top/bottom sản phẩm từng tháng của đội; SKU nào làm tăng/giảm doanh số nhiều nhất? — [SQL: S21](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
30. **V30** — SKU trọng tâm đạt bao nhiêu % target theo từng TDV và khách hàng; khoảng thiếu bao nhiêu? — [SQL: S46](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
31. **V31** — Sản phẩm nào nhiều khách mua nhưng lượng/đơn thấp; sản phẩm nào ít khách nhưng AOV cao? — [SQL: S23](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
32. **V32** — Cặp sản phẩm nào thường mua cùng; khách nào phù hợp bán combo nhưng chưa mua? — [SQL: S74](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
33. **V33** — Đơn nào bị hủy, trả, điều chỉnh, giao/hóa đơn chậm hoặc chưa tìm thấy hóa đơn? — [SQL: S42](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
34. **V34** — Chương trình khuyến mãi nào đội đang dùng; khách tham gia, số đơn và doanh thu trước–trong–sau chương trình thế nào? — [SQL: S12](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
35. **V35** — Tổng nợ và nợ quá hạn của đội theo tháng; khách nào mới chuyển sang nhóm tuổi nợ xấu hơn? — [SQL: S25](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
36. **V36** — Khách nào vừa nợ quá hạn vừa giảm mua; TDV phụ trách và số tiền cần thu là bao nhiêu? — [SQL: S26](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
37. **V37** — Thu tiền tháng này của từng TDV/khách so kế hoạch; cam kết thu nào đã quá hạn? — [SQL: S45](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
38. **V38** — SKU khách đang cần nhưng kho thiếu là gì; đơn/doanh thu nào có nguy cơ mất vì thiếu hàng? — [SQL: S47](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
39. **V39** — SKU tồn cao/chậm bán/cận date trong phạm vi vùng là gì; khách nào phù hợp để xử lý tồn? — [SQL: S28](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)
40. **V40** — Cuối tháng, những ngoại lệ nào chưa xử lý: target thiếu, khách chưa gán, đơn chưa hóa đơn, nợ xấu, hàng trả và dữ liệu chưa đồng bộ? — [SQL: S76](./bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md)

## 6. Ma trận mức sẵn sàng dữ liệu

### Nhóm A — Có thể ưu tiên ngay từ nguồn đã thấy trong repo/catalog

- Doanh thu theo tháng/kênh/miền/tỉnh/chi nhánh/nhân viên/khách hàng/sản phẩm.
- Số đơn, AOV, hàng trả/điều chỉnh, top/bottom và so sánh kỳ.
- KPI, target và phân tầng 65/70/80/100/120 theo snapshot có kỳ.
- Khách mới/mua lại/hoạt động theo cờ KPI; khách mua lần đầu theo lịch sử hóa đơn.
- Công nợ hiện tại, tuổi nợ, khách rủi ro và độ tập trung công nợ.
- Tồn kho snapshot, months-to-sell, tồn âm/chậm luân chuyển ở mức hiện có.
- Khuyến mãi theo chuỗi DMS–đơn–hóa đơn trong phạm vi thời gian nguồn có độ phủ.
- Hợp đồng ETC, kế hoạch ETC và thực hiện doanh thu ở mức các bảng đã map được.

### Nhóm B — Có dữ liệu gốc nhưng cần mart/công thức nghiệp vụ chuẩn

- Growth bridge theo khách/sản phẩm/kênh/miền và price–volume–mix.
- Cohort giữ chân 1/3/6/12 tháng, tái kích hoạt, chu kỳ mua và churn theo từng phân khúc.
- Like-for-like growth, độ phủ, cross-sell, benchmark khách/địa bàn tương đồng.
- Run-rate và gap-to-target; streak tăng/giảm 3–6 tháng.
- Năng suất đội/nhân viên, ảnh hưởng chuyển địa bàn/chuyển người phụ trách.
- Uplift khuyến mãi so baseline; phải chốt cách chọn nhóm/kỳ đối chứng.
- Stock-out và lost sales; phải thống nhất cách nhận biết nhu cầu không được đáp ứng.
- Theo dõi thực hiện hợp đồng/thầu ETC; cần thống nhất trạng thái và giá trị chuẩn.

### Nhóm C — Chưa thấy nguồn chuẩn hoặc lịch sử đủ trong catalog hiện tại, cần DNH xác nhận/map thêm

- Doanh thu thuần đầy đủ, chiết khấu thương mại, giá vốn, lợi nhuận gộp và biên lợi nhuận.
- Hạn dùng theo lô/cận date đầy đủ cho tất cả tồn kho.
- Lịch sử công nợ và thu tiền theo snapshot tháng để tính đúng DSO, roll-rate nhóm tuổi và cam kết thu.
- Lịch sử route/visit/call và kết quả viếng thăm để tính năng suất tuyến bán hàng.
- Kế hoạch thầu, kết quả trúng/thua, ngày hiệu lực/hết hạn và giá trị hợp đồng còn lại chuẩn.
- Dữ liệu thị trường/đối thủ để tính market share và share-of-wallet thực ngoài DNH.
- Forecast chính thức và xác suất đạt; hệ thống hiện đang chặn câu hỏi dự báo tương lai.
- Lịch sử headcount/nhân sự vào–ra/chuyển vùng để phân tích năng suất sau điều chỉnh tổ chức.

## 7. Thứ tự triển khai khuyến nghị

1. **P0 — Monthly scorecard:** C01–C12, M01–M10, V01–V10.
2. **P0 — Drill-down nguyên nhân:** C21–C36, M11–M35, V11–V34.
3. **P0 — Công nợ và ngoại lệ:** C37–C40, M37–M38, V35–V40.
4. **P1 — Tồn kho/ETC:** C41–C44, M39–M42.
5. **P1 — Dự báo và action tracker:** C50–C52, M43–M44.
6. **P2 — Lợi nhuận, field force và market share:** C13–C20, C45–C49 sau khi chốt nguồn dữ liệu.

Master list này gồm **138 câu hỏi**: 54 câu C-level, 44 câu TP/Giám đốc miền/Giám đốc kênh và
40 câu Quản lý vùng. Không cần biến cả 138 câu thành 138 báo cáo riêng: nên thiết kế khoảng
10–15 mart/metric chuẩn và cho phép drill-down theo các chiều đã nêu ở mục 2.
