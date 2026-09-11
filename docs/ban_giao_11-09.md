# Bàn giao 11/09/2026 — phần scripts, SQL đối chứng, tài liệu

Theo phân công trong kế hoạch chốt UAT 11–20/09: phần này không sửa `backend/`, không deploy, không gọi API trả
phí, không sửa sheet. Mọi con số dưới đây đo trên Bravo (chỉ đọc) hoặc kho local; nguồn nào ghi rõ nguồn đó.

## 1. Commit trong ngày

| Commit | Nội dung |
|---|---|
| `ab2c04a` | Đánh dấu hai tài liệu còn mẫu số 119 là đã bị thay thế bởi phạm vi 126 |
| `81e43f1`, `c3b15cf` | S26 so tháng tròn; đính chính số liệu S26; sổ theo dõi 126 câu |
| `7798b6a` | Gỡ và cấm business-eval; tách `scripts/nhat_ky_eval.py` để runner 138 câu không hỏng theo |
| `99079af` | `AGENTS.md`: cấm sửa code trực tiếp trên máy 24; khóa quy tắc V25 dừng từ 01/07/2026 |
| `3b965c1` | V03 chuyển sang S59 (doanh số từng ngày so nhịp); M28 chuyển sang S75 (tỷ lệ theo tháng) |
| `901aa42` | Runner 126 câu có trần chi phí, tài khoản theo nhóm, chế độ chạy thử |
| `1917c8e` | S11, S55, S58, S64 đếm tháng rải rác thành chuỗi liên tiếp — đã sửa |

Full test cuối ngày: 538 passed, 1 deselected (`test_chay_dry_run_tat_ca_audiences` gắn `integration` vì cần DB
thật; `pyproject.toml` loại nhóm này khỏi lần chạy mặc định).

## 2. Cổng kiểm miễn phí (mục 11h00)

| Cổng | Kết quả | Ghi chú |
|---|---|---|
| Định tuyến 138 câu | ĐẠT | 135/138 có tool bắt buộc; 3 câu còn lại là nhóm dự báo S35 |
| Phạm vi kênh ETC | ĐẠT | chạy trên kho local |
| Tài khoản thiếu phạm vi | CHƯA ĐỦ NGUỒN | `auth.db` máy phát triển chỉ có tài khoản thử cũ — phải chạy trên máy 24 |
| Bất biến 41 tool | ĐẠT | 77/78; phép lệch là Bravo quá thời gian do tranh tải, chạy lại riêng thì qua |
| Độ mới nguồn Bravo (S37) | 5/6 nguồn đồng bộ lúc 09:00 11/09 | **Nguồn CTKM dừng ở 09/01/2026** |
| Health máy 24 | không kiểm được từ máy phát triển | theo log anh Đăng: `ok` |

## 3. Chatbot trên máy 24

- **Đang chạy đúng `f692e45`.** Mã băm nội dung hai file backend lúc 08:55:50 trùng khớp với `f692e45`; dịch vụ
  khởi động lại lúc 08:56:01. Kết quả tester chấm từ 08:56 ngày 11/09 gắn được với `f692e45`.
- Máy 24 đã về `master` (`99079af`); backend trên đĩa khớp code đang chạy, khởi động lại an toàn.
- Hai bộ sửa tay đã được cất lên GitHub, **chatbot đang chạy không có bộ nào**, chờ Codex review và gộp:
  - `may24-stash-truoc-f692e45` — sửa ngày 10/09: chặn gọi cả hai tool khách hàng cho C29 (từng ra 612 và 441
    "khách mới" trong cùng một câu), C30 cohort, `workforce_productivity`, `_inventory_supply_risk`, định tuyến,
    một tool mới.
  - `may24-sua-tay-1109` — sửa sáng 11/09. **Bỏ toàn bộ phần V25**: V25 dừng từ 01/07/2026 theo quyết định đã chốt,
    hai test `test_v25_*` hỏng trên nhánh này là đúng chức năng chặn. Hai tool mới chưa có trong catalog kiểm bất biến.
- Máy 24 còn 11 stash cũ khác, cái cũ nhất khoảng 14/08 — có thể còn bản sửa chưa từng lên git.
- Các câu chấm đạt ngày 10/09 (M26, M31, M34, M41, V06, V07, V08, C39) có thể đã chấm trên code sửa tay mà chatbot
  hiện không còn chạy. Vòng nền 14/09 chấm lại toàn bộ 126 câu nên tự xử lý.

## 4. Checker sửa hôm nay và câu phải chấm lại

| Checker | Câu | Lỗi | Hệ quả |
|---|---|---|---|
| S26 | C39, M38, V36 | So 4 ngày tháng 9 với cả tháng 8; kho local thiếu 48% tháng 7 | Đúng: 1.647 khách vừa nợ quá hạn vừa giảm mua, tổng nợ quá hạn 20.312.995.881đ (nợ snapshot 04/09, doanh thu T8/T7 từ Bravo). C39 đang ghi đạt → chấm lại |
| S55 | M16, V13 | Đếm tháng giảm rải rác thành chuỗi; không lọc miền | Miền MB hiện **1 người** giảm ≥3 tháng liên tiếp (Phạm Xuân Toàn, HPO1, 05→08/2026), 3 người ≥2. Nhận xét "chatbot chỉ nêu 1 người" dựa trên checker lỗi |
| S58 | M05 | Đếm tháng rải rác | Không vùng nào quá 3 tháng liên tiếp (MB 05→07/2026, hụt 31,5 tỷ). M05 đang ghi đạt → chấm lại |
| S64 | C47 | Đếm tháng rải rác | Người dưới 80% từ 6 tháng liên tiếp: 21, không phải 80. C47 đang ghi đạt → chấm lại |
| S11 | C16 | Đếm tháng rải rác | Chấm lại |
| S59 (mới cho V03) | V03 | S03 cũ sai hình dạng | Doanh số từng ngày đội MBKV2 tháng 9: 477.444.069đ / 230 đơn, **khớp đúng tổng `Amount_CT`** |
| S75 (mới cho M28) | M28 | S38 cũ sai chủ đề | Không gán TDV / không map vùng / không có trong DMS = 0 mọi tháng; mã người bán không có trong danh mục nhân viên 6,1–6,3% |

Sổ theo dõi `docs/uat_126_so_theo_doi_11-09.md`: đạt chắc 63/126, chờ chốt giới hạn 4, cần xác nhận 2, chờ kiểm 28,
chưa đạt 29.

## 5. Số đối chứng cho người chấm

Kết quả chạy nằm ở `outputs/doi_chung_AB_11-09/` trên máy phát triển (không commit): `M16_S55_sua_MB.md`,
`V11_S56_doi_MBKV2.md`, `C54_S38_toan_cty.md`, `V03_M28_S59_S75.md`, `streak_truoc.md` / `streak_sau.md`.
Chạy lại bất kỳ lúc nào bằng `scripts/chay_sql_doi_chung_138.py --checker <mã> [--area MB] [--manager MBKV2]`.

Hai lưu ý cho người chấm:
- V11 (S56): danh sách "từng TDV" của đội MBKV2 có cả dòng của chính QLV Phạm Xuân Tú (target tháng 12 là
  720 triệu). Cần thống nhất có tính dòng này hay không trước khi so.
- M28: "0%" và "khoảng 6%" đều có thể đúng, tùy "không gán TDV" hiểu là trống mã người bán hay mã không truy ra được TDV.

## 6. Việc cần người

| Ai | Việc |
|---|---|
| DNH | Nguồn CTKM dừng từ 09/01/2026 — C13, M35, M36, V34 chỉ trả được phần tới mốc đó |
| DNH | Đóng `EndDate` cho 65 dòng V25 trong `DIM_BacThuong` — chính các dòng này đã khiến bản sửa tay hiểu nhầm |
| DNH | V03: nhịp theo ngày lịch hay ngày làm việc (câu 1 trong `DNH_can_xac_nhan_2_cau_han_10-09.md`) |
| Người chấm / PMO | Chốt cách hiểu M28 và cách tính dòng QLV trong V11 |
| Máy 24 | Đếm số snapshot trong `fact_congno_khachhang_history` — đủ nhiều tháng thì C37/M37/V35 bớt bị chặn |
| Máy 24 | Chạy `scripts/kiem_tai_khoan_thieu_pham_vi.py` trên `auth.db` thật |
| Codex | Review và gộp hai nhánh sửa tay (bỏ V25), thêm tool mới vào catalog, full test xanh trước deploy 14/09 |
| Anh Đăng | Duyệt trần chi phí vòng nền 14/09 — ước tính khoảng 25 USD cho 126 câu |

## 7. Lưu ý dữ liệu

Kho local của máy phát triển có hóa đơn 01/07–04/09 và tháng 7 chỉ có 52% so với Bravo. Không dùng kho này để lấy
số chấm; các con số trong tài liệu này đã được đo lại trên Bravo hoặc ghi rõ nguồn.

## 8. Lệnh cho vòng nền 14/09

```powershell
python scripts/run_bo_138_cau.py --thu
python scripts/run_bo_138_cau.py --tran-chi-usd <trần> --nguoi-duyet "<người duyệt>" --label vong-nen-1409
```

`--thu` in kế hoạch chạy (126 câu = C-Level 46 + Giám đốc miền 42 + QLV 38, phạm vi tài khoản từng nhóm, chi phí ước
tính) và thoát, không gọi model. Chạy thật mà thiếu trần hoặc người duyệt thì runner từ chối trước khi gọi bất kỳ
lượt nào; chạm trần thì dừng và in lệnh `--resume`.
