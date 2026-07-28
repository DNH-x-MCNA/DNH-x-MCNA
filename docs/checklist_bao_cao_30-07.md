# Checklist chuẩn bị buổi báo cáo tiến độ 30/07/2026

Báo cáo chính: [`bao_cao_tien_do_16-30-07.md`](bao_cao_tien_do_16-30-07.md) · kỳ **16/07 → 30/07** (2 tuần, kể từ họp 16/07) — số liệu chốt đến
**28/07**, cần chạy lại để lấy số của ngày báo cáo.

---

## 1. Cập nhật số liệu (~5 phút, làm sáng 30/07)

```
set PYTHONIOENCODING=utf-8 && python scripts/demo1_ground_truth.py
```

Lấy từ output và thay vào bảng **"Số liệu hệ thống"** ở cuối báo cáo:

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

Hỏi chatbot bằng tài khoản `dnh`, **phiên chat mới**:

> Báo cáo chi phí AI toàn công ty

Điền vào Trang 1 mục D: tổng chi phí (USD + VNĐ), tổng số truy vấn, số phiên.

> Lưu ý khi trình bày: chi phí chỉ tính được cho các phiên **từ 28/07 trở đi** (trước đó hệ thống
> không nối được chi phí với người dùng). Nếu khách hỏi tổng chi phí từ đầu dự án thì phải nói rõ điều
> này, đừng để hiểu nhầm là chi phí thấp.

## 3. Kiểm tra hệ thống còn chạy tốt

```powershell
Get-NetTCPConnection -LocalPort 8010 -State Listen | Select-Object OwningProcess
```

Rồi thử 1 câu qua chatbot web để chắc chắn cả đường frontend → backend còn thông. Nếu lỗi, xem
[`server_deploy/RUNBOOK_congno_27-07.md`](../DNH-x-MCNA/backend/server_deploy/RUNBOOK_congno_27-07.md)
bên kho chatbot.

## 4. Việc chưa xong, cân nhắc hoàn tất trước 30/07

| Việc | Ảnh hưởng nếu để nguyên |
|---|---|
| **Giao diện Bảng điều khiển Chi phí AI** chưa lên web (chờ cập nhật lại phía nhà cung cấp hosting) | Không demo được màn hình này tại buổi báo cáo — chỉ trình bày qua chatbot dạng chữ |
| **Kiểm chứng trọn bộ 17 câu Demo #1** mới chạy được một phần | Chưa khẳng định được "đã kiểm chứng đầy đủ" ở Trang 3 |

---

## 5. Bốn đề nghị cần chốt với DNH tại buổi họp

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
  con số "9 lỗi · 3 lỗ hổng" là tổng của cả kỳ, đúng như trình bày trong báo cáo.
