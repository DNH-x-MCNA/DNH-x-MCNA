# Checklist chuẩn bị buổi báo cáo tiến độ 30/07/2026

Báo cáo chính: [`bao_cao_tien_do_30-07.md`](bao_cao_tien_do_30-07.md) — bản 7 slide theo template Google Slides. Kỳ **16/07 → 30/07** (2 tuần, kể từ họp 16/07). Số liệu chốt đến
**28/07**, cần chạy lại để lấy số của ngày báo cáo.

---

## 1. Cập nhật số liệu (~5 phút, làm sáng 30/07)

```
set PYTHONIOENCODING=utf-8 && python scripts/demo1_ground_truth.py
```

Lấy từ output và thay vào bảng **"Số liệu hệ thống"** ở Slide 5:

| Lấy từ mục | Điền vào |
|---|---|
| `[C1]` | Doanh thu OTC / ETC / Tổng + số hóa đơn |
| `CÔNG NỢ` dòng `TOÀN CÔNG TY` | Tổng dư nợ · Nợ quá hạn · % |
| `[C7]` | 3 mốc: ≥100% · ≥80% · ≥65% |
| `[C6]` | Mức hoàn thành 3 miền + toàn đội |

Đổi luôn dòng tiêu đề `(… đến 28/07 …)` thành ngày chạy thật.

> ⚠️ **Không dùng cờ `--as-of`** cho báo cáo tiến độ — cờ đó chỉ dùng khi tập dượt Demo #1 cho tháng 7.
> Báo cáo 30/07 cần số thực tế đến ngày 30/07.

## 2. Cập nhật chi phí AI

**Nguồn số: bảng cước của nhà cung cấp AI (Anthropic Console → Usage/Cost), KHÔNG phải bảng điều khiển
nội bộ.** Mở Console, đọc *Total cost* của tháng, điền vào Slide 4.

Số chốt ngày 29/07: **26,01 USD ≈ 685 nghìn đồng** (kỳ 08/07 → 29/07, tỷ giá **26.334,50 đ/USD**). Chạy
lại sáng 30/07 để lấy số của đúng ngày họp.

> ⚠️ **Đừng lấy tổng chi phí từ dashboard nội bộ** — nó báo 14,51 USD trong khi hóa đơn thật là 26,01 USD.
>
> **Đã truy xong nguyên nhân 29/07, không phải lỗi:** đơn giá trong code khớp tuyệt đối với hóa đơn
> (cộng 4 loại token ra đúng 14,5134, lệch 0). Chênh 11,50 USD nằm trọn ở **08/07 → 14/07** — API đã dùng
> từ 08/07 nhưng tính năng đo chi phí đến **15/07** mới được viết (commit `d106a25`). Sổ nội bộ **không
> thiếu lượt nào kể từ khi bắt đầu đo**.
>
> → Tổng cả kỳ: lấy Console. Chi tiết theo người/theo ngày từ 15/07: lấy dashboard nội bộ. Cả hai đều
> đúng, chỉ khác phạm vi.

**Khi trình bày, nói rõ 2 điều** (đã ghi sẵn trong Slide 4):
- Đây là chi phí **giai đoạn phát triển/kiểm thử** của đội MCNA, chưa phải mức vận hành thật 147 TDV.
- Nhịp hiện tại ≈ **37 USD ≈ 965 nghìn đ/tháng**, sau 31/08 hết khuyến mãi thành **~55 USD ≈ 1,45 triệu
  đ/tháng** — đã vượt ngân sách 50 USD đang đặt trong hệ thống.

## 3. Kiểm tra hệ thống còn chạy tốt

```powershell
Get-NetTCPConnection -LocalPort 8010 -State Listen | Select-Object OwningProcess
```

Rồi thử 1 câu qua chatbot web để chắc chắn cả đường frontend → backend còn thông. Nếu lỗi, xem
[`server_deploy/RUNBOOK_congno_27-07.md`](../DNH-x-MCNA/backend/server_deploy/RUNBOOK_congno_27-07.md)
bên kho chatbot.

## 4. Việc chưa xong, cân nhắc hoàn tất trước 30/07

| Việc | Trạng thái |
|---|---|
| ~~Giao diện Bảng điều khiển Chi phí AI chưa lên web~~ | ✅ **XONG đêm 29/07** — đã lên web thật, demo được trực tiếp trên trình duyệt |
| ~~Kiểm chứng trọn bộ 17 câu Demo #1~~ | ✅ **XONG 29/07 — 17/17 đạt**, cả 3 vai trò |
| Đăng nhập bằng email + trang Quản lý Tài khoản *(mới, ngoài kế hoạch ban đầu)* | ✅ Deploy xong đêm 29/07, đã kiểm chứng trên máy chủ thật. **Không demo tab "Quên mật khẩu"** — máy chủ chưa có SMTP nên tính năng này cố ý không làm gì (không tự khoá tài khoản người dùng) |

---

## 5. Năm đề nghị cần chốt với DNH tại buổi họp

Xếp theo thứ tự ưu tiên — mục 1 là mới và gấp nhất:

**1. 🔴 Quyền xem của quản lý vùng** *(mới phát sinh tuần này, chặn Demo #1)*
> Quản lý vùng được xem số liệu ở phạm vi **đội của mình** hay **cả miền**?
> Riêng **tồn kho** và **công nợ** có thuộc quyền xem của họ không?

Hiện MCNA đã tạm chặn 9 báo cáo với tài khoản quản lý vùng để đảm bảo an toàn. Chưa chốt thì tại demo
không trình bày được phần đăng nhập vai quản lý vùng hỏi về doanh thu.

**2. 🔴 Cấp tài khoản cho quản lý vùng để nghiệm thu**
> Đề nghị DNH chỉ định 1–2 quản lý vùng nhận tài khoản, tự kiểm tra số liệu đội mình.

Đây là điểm đã nêu từ tuần trước, vẫn đang chờ. Không có bước này thì sai lệch (nếu có) sẽ chỉ phát
hiện ở nghiệm thu tháng 9.

**3. 🟠 Hai nhân viên có thể đang bị tính thiếu lương**
> Đề nghị bộ phận lương/kế toán đối chiếu 2 mã nhân viên đã gửi và sửa dữ liệu gốc.

**4. 🟠 Xác nhận văn bản chính sách lương áp dụng cho tháng 7**
> Có 2 phiên bản cùng tồn tại. Cấu hình hệ thống tính lương thật của DNH nghiêng về bản mới (hiệu lực
> 01/07) — đề nghị xác nhận chính thức.

**5. 🆕 🟠 Một nhân viên bán hàng nhưng không được đặt chỉ tiêu** *(phát hiện 29/07)*
> Mã `TM26060104` — **Nguyễn Văn Dũng (NTH01)** có doanh số thật **4.952.381đ** nhưng chỉ tiêu tháng
> bằng **0**, nên không xuất hiện trong bất kỳ thống kê KPI nào.

Đây là lý do tổng nhân viên là **148** nhưng số tính KPI chỉ **147**. Nếu là nhân viên mới chưa kịp giao
chỉ tiêu thì cần bổ sung; nếu thuộc diện không giao chỉ tiêu thì cần xác nhận để hệ thống ghi nhận đúng.

**6. 🔵 Xin hộp thư gửi email cho hệ thống** *(mới, không gấp)*
> Đề nghị IT của DNH cấp 1 hộp thư `@namhapharma.com` kèm **app password** để hệ thống gửi được mật
> khẩu tự động.

Không có nó thì tính năng "Quên mật khẩu" không hoạt động, và việc tạo tài khoản mới phải chuyển mật
khẩu tay. Có thể chốt sau, không chặn Demo #1.

---

## 6. Điểm cần nói rõ, tránh hiểu nhầm

- **"Chỉ tiêu đạt thấp" không phải hệ thống sai.** Con số đạt chỉ tiêu so lũy kế đến hiện tại với chỉ
  tiêu **cả tháng**. Giữa tháng luôn thấp, cuối tháng mới phản ánh đúng. Nếu khách hỏi lúc đầu tháng,
  con số gần như bằng 0 — đúng về số học nhưng dễ gây hiểu sai.
- **Chi phí AI sẽ tăng ~50% sau 31/08.** Nêu chủ động, kèm việc MCNA đang tối ưu phần dữ liệu nạp vào
  để bù lại. Đừng để khách thấy con số thấp hôm nay rồi bất ngờ về sau.
- **Cả 3 lỗ hổng phân quyền do MCNA tự tìm ra và tự sửa**, không phải khách phát hiện — nên trình bày
  như bằng chứng của quy trình tự rà soát, không phải sự cố.
- **Kỳ báo cáo là 2 tuần (16/07 → 30/07)**, không phải 1 tuần. Nếu khách nhớ mốc họp trước là 16/07 thì
  con số "10 lỗi · 3 lỗ hổng" là tổng của cả kỳ, đúng như trình bày trong báo cáo.
