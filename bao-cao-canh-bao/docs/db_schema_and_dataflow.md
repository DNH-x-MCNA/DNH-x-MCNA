# DNH — Kiến trúc CSDL & Luồng dữ liệu (thực tế, lớp hậu-ETL)

> Tài liệu này mô tả **kiến trúc dữ liệu THỰC TẾ đang chạy** (khảo sát trực tiếp 42 bảng
> trên lớp hậu-ETL, số dòng thật). Thay thế `database_design.md` — vốn là thiết kế SQL Server
> lý tưởng (tên `customers`/`employees`/`receivable_etc`) **không khớp** lớp hậu-ETL hiện tại.

## 1. Luồng dữ liệu tổng thể

```
Bravo (OTC)  ─┐
Bravo SX (ETC)─┼──▶  [ ETL bên thứ ba, máy chủ vật lý riêng ]  ──▶  Lớp hậu-ETL  ──(view)──▶  Supabase (Postgres)
DMS          ─┘         · trích xuất · làm sạch · dựng mart          (42 bảng)                        │
                        · chu kỳ ~1 GIỜ/lần                                                          │
                                                                                    ┌───────────────┼───────────────┐
                                                                              AI Chatbot      Web Dashboard     Alert Engine
                                                                             (NL2SQL,        (đọc mart:        (17 trigger,
                                                                              raw + view)     receivable/       gate bằng
                                                                                              inventory/kpi)    watermark)
```

- **Một chiều, chỉ đọc**: không ứng dụng nào ghi ngược Bravo/DMS.
- **Nhịp thật = 1 giờ** (do ETL thượng nguồn), nên alert real-time tối đa tươi theo giờ →
  alert gate bằng watermark `MAX("SyncAt")`, chỉ chạy khi có refresh mới (xem `check_etl_freshness_alert`).
- **Supabase là VIEW của lớp hậu-ETL**, không phải mirror thô của Bravo/DMS.

## 2. Phân lớp 42 bảng

| Lớp | Tiền tố | Vai trò | Cột tracking (incremental) |
|---|---|---|---|
| Raw · Bravo OTC | `brv_*` | Bản sao hóa đơn/đơn hàng/KH/SP OTC | ✅ Id, CreatedAt, ModifiedAt, SyncAt |
| Raw · Bravo SX (ETC) | `brvsx_*` | Hóa đơn ETC, thẻ kho lô, trả hàng, ứng trước | ✅ |
| Raw · DMS | `dms_*`, `dmssx_*` | Khách hàng & đơn hàng phân phối | ✅ |
| Dimensions | `dim_*` | Nhân viên, tỉnh/thành, địa bàn, target vùng, nhóm SP | một phần |
| Facts | `fact_*` | Tổng hợp KH + chỉ tiêu (nguồn KPI), kế hoạch ETC | SaveDate (mốc kỳ) |
| Marts & Views | `receivable_*`, `inventory`, `kpi_*`, `vw_*` | **Nguồn cho ứng dụng** | rebuild theo kỳ |
| Lớp sạch / di sản | `customers`, `regions`, `employees`, `orders`, `invoices`, `contracts` | Schema cũ + mock demo — **KHÔNG phải nguồn go-live** | — |

### Bảng cốt lõi ứng dụng dùng trực tiếp (★)
- `receivable_detail` (165k) — công nợ OTC theo kỳ + tuổi nợ (bucket `overdue_1_15…overdue_gt_45`).
- `inventory` (211) — tồn kho snapshot (`closing_qty`, `months_to_sell`).
- `kpi_summary` (58) — KPI rollup tháng/quý/năm; nguồn tính từ `fact_tonghopkhachhang`.
- `vw_hoadon_otc` (181k) / `vw_hoadon_etc` (2.5k) — hóa đơn đã hợp nhất header+detail.
- `dim_nhanvien`, `dim_tinhthanhpho`, `brv_sanpham`, `brv_trangthaiduyet/hoadon` (dim trạng thái để lọc hủy).

## 3. Ranh giới đọc của từng ứng dụng
- **Web Dashboard** (`backend/main.py`): đọc mart `receivable_detail` / `inventory` / `kpi_summary`.
- **AI Chatbot** (`ai_agent/chatbot.py`): join raw `brv_/brvsx_hoadonct + hoadonhdr` (+ dim) cho truy vấn hóa đơn chi tiết; có thể chuyển sang `vw_hoadon_*` để đơn giản.
- **Alert Engine** (`src/alerts.py` + `main.py`): đọc mart + raw; gate bằng watermark; guard `check_data_sanity_ok` chặn nếu mart rỗng.

## 4. Data gaps (đã biết, cần bổ sung dữ liệu — không phải bug code)
1. **Hạn mức tín dụng**: mart không có; nhưng `customers.daily_debt_limit`/`allowed_debt_days` (lớp di sản) có — xác nhận thật/mock rồi đưa vào mart để bật cảnh báo #5 (`check_credit_limit_exceeded_alert`).
2. **Hạn dùng lô (cận date)**: `brvsx_thekholot` có mã lô + số lượng nhưng **thiếu ExpiryDate**. Cần map lô→hạn dùng (dữ liệu này có ở `brvsx_tralai` nhưng chỉ cho hàng trả) để bật `check_near_expiry_alert`. Quan trọng với dược.
3. **Hợp đồng thầu ETC**: `receivable_etc` có giá trị/đã trả nhưng thiếu ngày hết hạn HĐ + số lượng trúng thầu còn lại.

## 5. Khuyến nghị go-live (chốt ở các phiên trước)
- **Giữ lớp hậu-ETL làm nguồn**, KHÔNG dựng SQL Server on-prem 3-layer song song (trùng ETL đã có).
- Nếu cần tươi hơn 1 giờ: **tăng tần suất ETL sẵn có** (hoặc làm nó incremental) — không viết ETL thứ hai trỏ thẳng Bravo (tăng tải ERP production).
- Cân nhắc cho chatbot/alert dùng `vw_hoadon_*` thay vì tự join.

*(Xem thêm bản trực quan: Artifact "Kiến trúc CSDL & Data Flow".)*
