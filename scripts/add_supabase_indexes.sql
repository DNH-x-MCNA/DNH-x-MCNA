-- =====================================================================
-- DNH · Supabase — Index cho các bảng GỐC Bravo/DMS
-- =====================================================================
-- Mục đích: tăng tốc chatbot NL2SQL (join 187k × 47k × 69 dòng hiện không
--           có index → seq scan / hash join toàn bảng).
--
-- PHẠM VI AN TOÀN: chỉ index các bảng brv_* / brvsx_* / dms_* / fact_* —
--   đây là các bảng KHÔNG nằm trong vòng lặp đồng bộ của scripts/sync_daemon.py
--   (daemon chỉ replace: orders, invoices, receivable_detail/etc, inventory,
--    kpi_*, regions, employees, customers, contracts, appendices).
--   Vì vậy index thêm ở đây SẼ ĐƯỢC GIỮ, không bị xoá khi đồng bộ.
--
--   ⚠️ KHÔNG thêm index cho các bảng trung gian bị daemon replace — sẽ mất
--      sau lần sync kế tiếp; phần đó phải sửa trong sync_to_supabase.py (nhóm ②).
--
-- Cách chạy: dán toàn bộ file vào Supabase SQL Editor và Run. An toàn chạy lại
--   nhiều lần (dùng IF NOT EXISTS). Index tạo trên bảng vài trăm nghìn dòng
--   chỉ mất vài giây; các bảng này không bị daemon ghi nên khoá tạm là vô hại.
--
-- Rollback: xem phần DROP INDEX (đã comment) ở cuối file.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1) Hóa đơn OTC (brv_hoadonhdr 25.557 · brv_hoadonct 187.065)
--    Join: ct.Stt = hdr.Stt ; hdr.CustomerCode = dms_khachhang.Code ;
--          ct.ItemCode = brv_sanpham.Code
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_brv_hoadonhdr_customercode ON public.brv_hoadonhdr ("CustomerCode");
CREATE INDEX IF NOT EXISTS idx_brv_hoadonhdr_stt          ON public.brv_hoadonhdr ("Stt");
CREATE INDEX IF NOT EXISTS idx_brv_hoadonct_stt           ON public.brv_hoadonct  ("Stt");
CREATE INDEX IF NOT EXISTS idx_brv_hoadonct_itemcode      ON public.brv_hoadonct  ("ItemCode");

-- ---------------------------------------------------------------------
-- 2) Đơn hàng OTC (brv_donhang 26.671 · brv_donhangct 193.217)
--    Join: ct.BizDocId = donhang.BizDocId ; donhang.CustomerCode
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_brv_donhang_customercode   ON public.brv_donhang   ("CustomerCode");
CREATE INDEX IF NOT EXISTS idx_brv_donhang_bizdocid       ON public.brv_donhang   ("BizDocId");
CREATE INDEX IF NOT EXISTS idx_brv_donhangct_bizdocid     ON public.brv_donhangct ("BizDocId");
CREATE INDEX IF NOT EXISTS idx_brv_donhangct_itemcode     ON public.brv_donhangct ("ItemCode");

-- ---------------------------------------------------------------------
-- 3) Hóa đơn ETC (brvsx_hoadonhdr 2.448 · brvsx_hoadonct 9.919)
--    Join: ct.Stt = hdr.Stt ; hdr.CustomerCode = dmssx_khachhang.Code
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_brvsx_hoadonhdr_customercode ON public.brvsx_hoadonhdr ("CustomerCode");
CREATE INDEX IF NOT EXISTS idx_brvsx_hoadonct_stt           ON public.brvsx_hoadonct  ("Stt");
CREATE INDEX IF NOT EXISTS idx_brvsx_hoadonct_itemcode      ON public.brvsx_hoadonct  ("ItemCode");

-- ---------------------------------------------------------------------
-- 4) Khách hàng DMS (dms_khachhang 47.412 · dmssx_khachhang 39.967)
--    "Code" = đích join từ hóa đơn ; "CityId" = join sang dim_tinhthanhpho
--    (lọc vùng miền AreaCode qua tỉnh/thành)
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_dms_khachhang_code     ON public.dms_khachhang   ("Code");
CREATE INDEX IF NOT EXISTS idx_dms_khachhang_cityid   ON public.dms_khachhang   ("CityId");
CREATE INDEX IF NOT EXISTS idx_dmssx_khachhang_code   ON public.dmssx_khachhang ("Code");
CREATE INDEX IF NOT EXISTS idx_dmssx_khachhang_cityid ON public.dmssx_khachhang ("CityId");

-- ---------------------------------------------------------------------
-- 5) KPI tổng hợp (fact_tonghopkhachhang 38.249)
--    Join: EmployeeCode = dim_nhanvien.EmployeeCode
--    Lọc:  SaveDate = '<cuối tháng>T00:00:00' (so khớp chuỗi chính xác)
-- ---------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_fact_thkh_employeecode ON public.fact_tonghopkhachhang ("EmployeeCode");
CREATE INDEX IF NOT EXISTS idx_fact_thkh_savedate     ON public.fact_tonghopkhachhang ("SaveDate");

-- ---------------------------------------------------------------------
-- Cập nhật thống kê để planner chọn index ngay lập tức
-- ---------------------------------------------------------------------
ANALYZE public.brv_hoadonhdr;
ANALYZE public.brv_hoadonct;
ANALYZE public.brv_donhang;
ANALYZE public.brv_donhangct;
ANALYZE public.brvsx_hoadonhdr;
ANALYZE public.brvsx_hoadonct;
ANALYZE public.dms_khachhang;
ANALYZE public.dmssx_khachhang;
ANALYZE public.fact_tonghopkhachhang;

-- ---------------------------------------------------------------------
-- Kiểm tra sau khi chạy: liệt kê index vừa tạo
-- ---------------------------------------------------------------------
-- SELECT tablename, indexname FROM pg_indexes
--  WHERE schemaname='public' AND indexname LIKE 'idx_%'
--  ORDER BY tablename, indexname;

-- =====================================================================
-- ROLLBACK (bỏ comment để gỡ toàn bộ index đã tạo)
-- =====================================================================
-- DROP INDEX IF EXISTS public.idx_brv_hoadonhdr_customercode;
-- DROP INDEX IF EXISTS public.idx_brv_hoadonhdr_stt;
-- DROP INDEX IF EXISTS public.idx_brv_hoadonct_stt;
-- DROP INDEX IF EXISTS public.idx_brv_hoadonct_itemcode;
-- DROP INDEX IF EXISTS public.idx_brv_donhang_customercode;
-- DROP INDEX IF EXISTS public.idx_brv_donhang_bizdocid;
-- DROP INDEX IF EXISTS public.idx_brv_donhangct_bizdocid;
-- DROP INDEX IF EXISTS public.idx_brv_donhangct_itemcode;
-- DROP INDEX IF EXISTS public.idx_brvsx_hoadonhdr_customercode;
-- DROP INDEX IF EXISTS public.idx_brvsx_hoadonct_stt;
-- DROP INDEX IF EXISTS public.idx_brvsx_hoadonct_itemcode;
-- DROP INDEX IF EXISTS public.idx_dms_khachhang_code;
-- DROP INDEX IF EXISTS public.idx_dms_khachhang_cityid;
-- DROP INDEX IF EXISTS public.idx_dmssx_khachhang_code;
-- DROP INDEX IF EXISTS public.idx_dmssx_khachhang_cityid;
-- DROP INDEX IF EXISTS public.idx_fact_thkh_employeecode;
-- DROP INDEX IF EXISTS public.idx_fact_thkh_savedate;
