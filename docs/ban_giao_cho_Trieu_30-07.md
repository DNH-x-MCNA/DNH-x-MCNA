# Bàn giao cho Triều — buổi họp 30/07/2026

Đăng không thuyết trình hôm nay, Triều trình bày thay. Tài liệu này gom lại mọi thứ cần biết trước khi
vào họp — đọc file này là đủ, không cần đọc lại từng commit.

---

## 1. Việc cần làm TRƯỚC khi họp (~15-20 phút)

Theo đúng thứ tự trong [`checklist_bao_cao_30-07.md`](checklist_bao_cao_30-07.md):

1. **Chạy lấy số mới nhất:**
   ```
   set PYTHONIOENCODING=utf-8 && python scripts/demo1_ground_truth.py
   ```
   Điền vào Slide 5 của [`bao_cao_tien_do_30-07.md`](bao_cao_tien_do_30-07.md) — bảng đối chiếu mục nào
   vào ô nào đã ghi sẵn trong checklist. **Không dùng cờ `--as-of`** — báo cáo cần số thực tế đến hôm nay.

2. **Lấy chi phí AI từ Anthropic Console** (không lấy từ dashboard nội bộ — xem mục 3 bên dưới), điền
   vào Slide 4.

3. **Kiểm hệ thống còn sống:**
   ```powershell
   Get-NetTCPConnection -LocalPort 8010 -State Listen | Select-Object OwningProcess
   ```
   Rồi thử 1 câu qua chatbot web bằng phiên mới để chắc frontend → backend còn thông.

---

## 2. Cái MỚI nhất — đêm 29/07, chưa có trong bản báo cáo cũ nếu Triều đọc trước đó

Nếu Triều từng xem báo cáo trước 29/07 tối, ba thứ sau là mới hoàn toàn:

### a) Đăng nhập bằng email + trang Quản lý Tài khoản

- Nhân viên đăng nhập được bằng `nhanvien@namhapharma.com` hoặc username cũ (cả hai đều dùng được).
- Ban điều hành có nút **"Quản lý Tài khoản"** trên header web → tạo tài khoản mới, phân quyền, khoá/mở.
- **Tự đăng ký công khai bị tắt có chủ ý** — nếu khách hỏi "sao không cho nhân viên tự đăng ký", trả
  lời: *Bravo không lưu email nhân viên nên hệ thống không biết gán quyền gì cho người vừa đăng ký; phải
  do Ban điều hành tạo tài khoản và gán quyền trực tiếp.*

**⚠️ ĐỪNG DEMO tab "Quên mật khẩu".** Máy chủ chưa có hộp thư gửi mail (`SMTP`), nên tính năng này *cố
ý không làm gì cả* để tránh tự khoá tài khoản người dùng — bấm vào sẽ thấy im lặng, trông như hỏng. Đây
là lý do trong đề nghị số 6 (xin hộp thư `@namhapharma.com` + app password).

**Luồng DÙNG ĐƯỢC để demo:** Quản lý Tài khoản → Tạo tài khoản mới. Mật khẩu hiện thẳng trên màn hình
cho admin đọc và chuyển tay — không cần chờ email.

### b) Giao diện chatbot làm lại toàn bộ

Đổi sang bảng màu Dược Nam Hà, số liệu tài chính căn cột thẳng hàng, bảng dữ liệu có nhãn màu theo kênh/
vùng. Nếu Triều thấy giao diện khác hẳn lần trước xem — đây là chủ ý, không phải lỗi hiển thị.

### c) Dashboard Chi phí AI đã lên web thật

Trước đây (checklist bản cũ) ghi "chưa lên web, chỉ demo qua chatbot dạng chữ" — **giờ đã lên**, demo
trực tiếp trên trình duyệt được, không cần gõ câu hỏi.

---

## 3. Bẫy dễ dính khi khách hỏi

| Khách hỏi/nghi ngờ | ĐỪNG nói | NÊN nói |
|---|---|---|
| "Sao chi phí AI thấp vậy, tưởng tốn hơn?" | Im lặng dùng số dashboard nội bộ (14,51 USD) | Dùng số **Anthropic Console** (26,01 USD) — đây là hoá đơn thật. Dashboard nội bộ chỉ thiếu 7 ngày đầu tháng (trước khi có code đo), không phải sai |
| "Đạt chỉ tiêu sao thấp thế, đầu tháng mà" | — | Con số so **luỹ kế đến hiện tại** với chỉ tiêu **cả tháng** — đúng về số học, cuối tháng mới phản ánh đúng |
| "3 lỗ hổng bảo mật này ai phát hiện?" | — | **MCNA tự rà soát phát hiện**, không phải khách báo — đây là bằng chứng quy trình tự kiểm, không phải sự cố |
| "Sao giờ mới tính được chi phí AI?" | — | Chủ động nói: sau 31/08 hết khuyến mãi, chi phí sẽ tăng ~50% thành **~55 USD/tháng, đã vượt ngân sách 50 USD** đang đặt. Đừng để khách thấy số thấp hôm nay rồi bất ngờ sau |
| "Kỳ báo cáo này bao lâu?" | — | **2 tuần** (16/07 → 30/07), không phải 1 tuần — nếu khách nhớ mốc họp trước là 16/07 |

---

## 4. Nếu khách hỏi sâu về phân quyền theo lớp

DNH tuần trước có yêu cầu làm dữ liệu theo từng lớp và chỉ rõ đang xử lý ở lớp nào. Đã có tài liệu riêng:
[`ban_do_kiem_soat_theo_lop.md`](ban_do_kiem_soat_theo_lop.md).

**Câu trả lời ngắn nếu bị hỏi thẳng:**
> Luồng dữ liệu đang xử lý ở **Lớp 3 — Quản lý vùng**. Lớp 4 (148 TDV) đã đóng từ 20/07. Lớp 1–2 tự
> kiểm xong, sai lệch 0 đồng, đang chờ anh Long soát. Toàn bộ việc đang mở — 3 lỗ hổng phân quyền, phạm
> vi xem của quản lý vùng — đều nằm ở Lớp 3.

---

## 5. Năm (thực ra sáu) đề nghị cần khách chốt

Đã có bảng đầy đủ trong [`checklist_bao_cao_30-07.md`](checklist_bao_cao_30-07.md) mục 5. Quan trọng
nhất — **mục 1** — nếu không chốt được thì nói rõ: Demo #1 ngày 09/08 sẽ không trình bày được phần đăng
nhập vai quản lý vùng.

Mục 6 (xin hộp thư gửi email) là mới thêm sáng nay, không gấp — chỉ nêu nếu còn thời gian.

---

## 6. Ghi biên bản

Có sẵn khung: [`bien_ban_hop_30-07.md`](bien_ban_hop_30-07.md) — phần 1 (nội dung MCNA báo cáo) và phần
2 (bảng đề nghị) đã điền sẵn, chỉ cần điền tại chỗ: người tham dự, ý kiến DNH, phân công, mốc tiếp theo.

---

## 7. Nếu có sự cố kỹ thuật giữa buổi họp

- Chatbot không trả lời / lỗi 500: kiểm tra cổng 8010 còn nghe không (lệnh ở mục 1.3). Nếu backend chết,
  xem [`server_deploy/RUNBOOK_congno_27-07.md`](../DNH-x-MCNA/backend/server_deploy/RUNBOOK_congno_27-07.md)
  bên kho `DNH-x-MCNA`.
- Giao diện web không cập nhật: có thể Vercel đang build lại, đợi vài phút hoặc dùng bản đã cache.
- Đừng tự ý chạy `create_admin.py` hay bất kỳ script `create_*`/`seed_*` trên máy chủ trong lúc họp —
  các script này có thể đổi mật khẩu hoặc ghi dữ liệu giả đè lên dữ liệu thật.
