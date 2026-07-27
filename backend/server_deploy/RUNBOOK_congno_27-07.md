# RUNBOOK — Triển khai R-B (công nợ vào chatbot) + việc chạy trên máy chủ live
### Tuần T5 27–31/07/2026 · chạy trên `C:\dnh_chatbot` (máy chủ live)

Code R-B đã viết xong và test logic trên máy dev (`D:\DNH-x-MCNA\backend`). Các bước dưới đây **phải
chạy trên máy chủ live** vì cần tài khoản Bravo của chatbot + VPN (máy dev không nối được Bravo).

---

## 0. VIỆC GẤP THỨ HAI (làm trước, ~15 phút) — không liên quan R-B

### 0.1 Sao lưu lịch sử chi phí AI (mất là mất trắng)
`backend/logs/cost_log.jsonl` bị `.gitignore` loại, **chỉ tồn tại trên máy chủ**; deploy xoá `logs/`
là mất sạch nguyên liệu ước tính chi phí go-live. Sao lưu ra ngoài thư mục deploy TRƯỚC khi làm gì:
```powershell
Copy-Item C:\dnh_chatbot\backend\logs\cost_log.jsonl `
          C:\dnh_backup\cost_log_$(Get-Date -Format yyyyMMdd).jsonl
```
Sau đó chạy thử công cụ đọc chi phí (mới viết — mục 5):
```powershell
cd C:\dnh_chatbot\backend ; py cost_report.py --by-user --top 15
```

### 0.2 🔴 RÒ RỈ MẬT KHẨU — XỬ LÝ NGAY (phát hiện 27/07)
54 file trong `bao-cao-canh-bao/scripts/*.py` **hardcode mật khẩu Supabase** và **đã commit + push lên
GitHub** (`github.com/DNH-x-MCNA/DNH-x-MCNA`). Chuỗi lộ:
`postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-...pooler.supabase.com:5432/postgres`

Đây là mật khẩu DB thật, đang nằm trong lịch sử git công khai. Cần (theo thứ tự):
1. **Đổi mật khẩu Supabase NGAY** (Dashboard → Database → Reset password) — coi như đã lộ.
2. Cập nhật mật khẩu mới vào `.env` của mọi nơi dùng (không hardcode lại).
3. Sửa 54 script đọc từ `os.environ`/`.env` thay vì chuỗi cứng (hoặc xoá nếu chỉ là script dò 1 lần).
4. Cân nhắc purge lịch sử (git filter-repo) nếu repo còn được chia sẻ — nhưng **đổi mật khẩu là bước
   bắt buộc và đủ để chặn rủi ro tức thời**, purge chỉ là dọn dẹp.

> Không tự đổi/commit hộ ở đây vì cần quyền tài khoản Supabase + xác nhận của anh Triệu (chủ script).

---

## 1. 🔴 SPIKE CHẶN — chạy ĐẦU TIÊN, trước khi deploy R-B (~5 phút)

Xác nhận tài khoản Bravo **của chatbot** (biến `BRAVO_*` trong `.env`, KHÁC `BRAVO_SQL_*` bên `D:\DNH`)
có quyền `EXECUTE` SP và đo thời gian chạy:
```powershell
cd C:\dnh_chatbot\backend ; py spike_congno_sp.py
```
Đọc kết quả:
- **Thiếu quyền EXECUTE** → dừng, xin DNH cấp quyền `EXECUTE` trên `usp_DeptAccDueDate_GetData` cho
  tài khoản chatbot. Đây là việc chờ khách, không giải bằng code. (Phương án lùi: job bên `D:\DNH`
  đẩy kết quả SP lên — chỉ dùng khi kẹt.)
- **SP không thấy trong DB** → kiểm `BRAVO_DATABASE` (kế hoạch: `NH_Report_TM`).
- **Thời gian chạy** quyết định lịch đồng bộ (mục 3).

Ghi lại: số dòng, tổng `CloseBal`, tổng `OverDueAmount` (để đối chiếu bước 4 tầng 1).

---

## 2. Deploy code R-B

```powershell
cd C:\dnh_chatbot
git status                 # máy chủ TỪNG có code chưa commit — kiểm trước khi pull, đừng đè mất
git pull
cd backend
py local_warehouse.py      # tạo bảng fact_congno_khachhang (idempotent, an toàn chạy lại)
```
Bảng mới **không tự có** khi pull — bắt buộc chạy `local_warehouse.py` (init schema).

---

## 3. Chạy đồng bộ công nợ

**Đã đo SP từ máy dev 27/07: 15,1 giây (9.894 dòng)** → dưới 20s và dưới timeout 90s, nên dùng ca đơn
giản nhất, **không cần lịch riêng** — công nợ gọi luôn trong `main()`:
```powershell
py sync_warehouse.py            # sync đầy đủ, gồm cả công nợ (bọc try/except riêng)
```
Kỳ vọng in ra: `[fact_congno_khachhang] Snapshot YYYY-MM-DD: N dòng (dư nợ ..., quá hạn ...)`.

> Cờ `--congno-only` (lịch riêng timeout 300s) chỉ dùng nếu sau này SP chậm lên > 60s — hiện chưa cần.

---

## 4. KIỂM CHỨNG — ba tầng

> ✅ **Tầng 1 + tầng 2 đã kiểm từ máy dev 27/07 (BRAVO_SQL_*): map cột lệch 0,00 đồng** so với nguồn
> chuẩn `alerts.py::get_bravo_receivables_snapshot`. Trên máy chủ chỉ cần chạy lại để xác nhận tài
> khoản chatbot ra cùng số. Số đo 27/07: tổng dư nợ 179,66 tỷ · quá hạn 79,32 tỷ (44,1%); OTC 32,4%
> · ETC 45,2% quá hạn.

### Tầng 1 — cùng tiến trình (mạnh nhất)
Gọi SP tươi (spike mục 1) rồi truy vấn ngay bảng local vừa đồng bộ:
- số dòng **bằng nhau tuyệt đối**;
- tổng dư nợ / quá hạn **lệch ≤ 1 đồng**; top 50 khách quá hạn **lệch 0 đồng**.
- Lệch hơn = lỗi map cột → sửa trước khi đi tiếp.

### Tầng 2 — chéo với báo cáo gốc (bằng chứng cho khách)
Chạy `scripts/demo1_ground_truth.py` bên `D:\DNH` trong vòng 15 phút sau khi đồng bộ:
- dư nợ / quá hạn lệch ≤ **0,05%**; tỷ lệ quá hạn lệch ≤ **0,1 điểm %**.
- **Mốc phân biệt nguồn:** nếu tỷ lệ quá hạn OTC/ETC ra **92,9%/81,1%** là vẫn đọc nguồn Excel cũ →
  sai. Nguồn đúng cho ra tỷ lệ **tầm 30–45%** (số cụ thể trôi theo ngày; 27/07 là 32,4%/45,2%).

### Tầng 3 — ca cụ thể
- **DTH00237** (BV Đa khoa Đồng Tháp) phải ra **số cụ thể** — 27/07 ra dư nợ 4,35 tỷ / quá hạn 0,78 tỷ
  (trước đây nguồn Supabase trả "chưa có dữ liệu"). ✅ đã xác nhận từ dev.
- **FPT Long Châu**: có nhiều chi nhánh (mã HCM…), cần biết đúng mã của ca "9,17→0,61 tỷ" để soi.
- Khách đang dư có không được xuất hiện như con nợ.

---

## 5. Kiểm chứng đầu-cuối qua chatbot thật (phiên MỚI, 3 loại tài khoản)

Mở phiên chat mới mỗi lượt (hỏi lại phiên cũ = nhận câu trả lời cũ từ bộ nhớ hội thoại), đối chiếu
`backend/logs/audit_log.jsonl`:
- Hỏi công nợ **1 khách** → có số + mốc thời gian, **không** còn cảnh báo "bảng nhập tay có thể sai".
- Hỏi **tổng công nợ / top khách nợ** → khớp tầng 2; log xác nhận đọc kho local (tool
  `get_receivables_overview` / `query_database`), **không** phải Supabase.
- Ép AI đọc nguồn cũ ("tra bảng receivable_detail") → **phải bị chặn** (fail-closed ở `query_engine`).

## 6. Độ bền
- Tắt VPN rồi chạy đồng bộ → phải **giữ nguyên** snapshot cũ, không ghi đè bằng rỗng (SP 0 dòng →
  raise, giữ dữ liệu). *(đã test đường "bảng rỗng → unavailable" trên máy dev.)*
- Xoá sạch bảng thủ công → chatbot nói "chưa tra cứu được", tuyệt đối không nói "khách không có nợ".

## 7. Không hồi quy
```powershell
cd D:\DNH ; pytest tests/ -q          # 17 test + smoke ngưỡng theo vai trò vẫn pass
```

---

## Tóm tắt thay đổi code (đã ở trong git sau khi pull)
| File | Thay đổi |
|---|---|
| `local_warehouse.py` | + bảng `fact_congno_khachhang` (KH × kênh, 4 bucket + total_overdue) |
| `sync_warehouse.py` | + `sync_fact_congno()` (port SP từ `alerts.py`), cờ `--congno-only`, bọc try/except |
| `report_templates.py` | `_customer_receivable` đổi nguồn → kho local (4 trạng thái); + template `receivables_overview` |
| `schema_context.py` | + mô tả `fact_congno_khachhang`; bỏ `receivable_detail`/`receivable_etc` khỏi khối Supabase |
| `nl2sql.py` | định tuyến công nợ → `get_receivables_overview`/`query_database`; + định nghĩa tool |
| `query_engine.py` | **fail-closed**: chặn cứng mọi SQL đụng `receivable_detail`/`receivable_etc` |
| `cost_report.py` | (mới) đọc/tổng hợp chi phí AI — gộp theo phiên, nối user, giá sau khuyến mãi |
| `spike_congno_sp.py` | (mới) script spike quyền + timing + shape SP |
