-- ============================================================================
-- DNH — SCHEMA SUPABASE DEV (bản sao 6 tháng từ production, snapshot 2026-07-07)
-- ============================================================================
-- Mục đích: import vào công cụ vẽ schema (dbdiagram.io / DrawSQL / pgModeler)
-- hoặc chạy trực tiếp trên Supabase dev để bổ sung key + index (dev clone bằng
-- pandas to_sql nên nguyên bản KHÔNG có bất kỳ constraint/index nào).
--
-- Nguồn sự thật:
--   · Cấu trúc cột + kiểu dữ liệu: đọc trực tiếp information_schema của dev.
--   · PRIMARY KEY / UNIQUE: đã KIỂM CHỨNG uniqueness trên dữ liệu thật
--     (COUNT(DISTINCT) = COUNT(*), 0 NULL) — không suy đoán.
--   · FOREIGN KEY: lớp hậu-ETL KHÔNG có FK vật lý; các FK dưới đây là quan hệ
--     LOGIC mà code ứng dụng (chatbot/alerts) thực sự join — thêm vào để vẽ
--     sơ đồ quan hệ và (tùy chọn) ép toàn vẹn trên dev.
--   · INDEX: khớp bộ index production (docs/golive_phase0_source_tracking_mapping.md)
--     + bổ sung index DocDate (production đang THIẾU, là nguyên nhân các query
--     lọc theo tháng bị chậm/timeout khi clone).
--
-- Lưu ý kiểu dữ liệu: DocDate/ReleaseAt/StartDate... là TEXT (chuỗi ISO
-- 'YYYY-MM-DDTHH:MM:SS' giữ nguyên từ nguồn Bravo) — so sánh khoảng thời gian
-- trên chuỗi ISO vẫn đúng thứ tự và index vẫn dùng được.
-- ============================================================================

-- ============================================================
-- NHÓM RAW · BRAVO OTC (kênh nhà thuốc/bán lẻ)
-- ============================================================

-- Hóa đơn OTC — header (1 dòng = 1 hóa đơn, update-in-place, KHÔNG versioning)
CREATE TABLE brv_hoadonhdr (
    "Id"              bigint PRIMARY KEY,
    "BranchCode"      text,
    "Stt"             text NOT NULL UNIQUE,      -- mã chứng từ nghiệp vụ (khóa join với detail)
    "DocCode"         text,
    "DocDate"         text,                      -- ISO string 'YYYY-MM-DDT00:00:00'
    "DocNo"           text,                      -- số hóa đơn; RỖNG = chưa xuất số (DocStatus 9)
    "DMSId"           text,
    "DocStatus"       bigint,                    -- -> brv_trangthaiduyet.DocStatusKey
    "EmpDMSCode"      text,
    "EmpDMSCode2"     text,
    "EInvoiceStatus"  bigint,                    -- -> brv_trangthaihoadon.EInvoiceStatusKey
    "CustomerCode"    text,                      -- -> dms_khachhang.Code
    "IsActive"        boolean,
    "CreatedAt"       timestamp,
    "ModifiedAt"      timestamp,
    "TotalAmount"     double precision,
    "SyncAt"          timestamp,
    "Description"     text,
    "DistributorCode" text,
    "IsHC"            boolean                    -- TRUE = hóa đơn mock/HC, luôn lọc IsHC=FALSE
);

-- Hóa đơn OTC — chi tiết dòng hàng
CREATE TABLE brv_hoadonct (
    "Id"           bigint PRIMARY KEY,
    "Stt"          text NOT NULL,                -- -> brv_hoadonhdr.Stt
    "RowId"        text NOT NULL,
    "ItemCode"     text,                         -- -> brv_sanpham.Code
    "Unit"         text,
    "Quantity"     double precision,
    "UnitPrice"    double precision,
    "Amount9"      double precision,
    "TaxCode"      text,
    "TaxRate"      double precision,
    "Amount3"      double precision,
    "DiscountRate" double precision,
    "Amount4"      double precision,
    "Reduce"       double precision,
    "CTKM"         text,
    "CreatedAt"    timestamp,
    "ModifiedAt"   timestamp,
    "SyncAt"       timestamp,
    "Quantity9"    double precision,
    UNIQUE ("Stt", "RowId")
);

-- ============================================================
-- NHÓM RAW · BRAVO SX (kênh ETC — thầu/bệnh viện)
-- ============================================================

-- Hóa đơn ETC — header
CREATE TABLE brvsx_hoadonhdr (
    "Id"              bigint PRIMARY KEY,
    "BranchCode"      text,
    "Stt"             text NOT NULL UNIQUE,
    "DocCode"         text,
    "DocDate"         text,
    "DocNo"           text,
    "IsActive"        boolean,
    "CreatedAt"       timestamp,
    "ModifiedAt"      timestamp,
    "DMSId"           text,
    "DocStatus"       bigint,
    "EInvoiceStatus"  bigint,
    "CustomerCode"    text,                      -- -> dmssx_khachhang.Code (logic, Code có 1 trùng)
    "BizDocId_SO"     text,
    "TotalAmount"     double precision,
    "Description"     text,
    "WarehouseCode"   text,
    "SubBranchCode"   text,
    "SyncAt"          timestamp,
    "DistributorCode" text
);

-- Hóa đơn ETC — chi tiết dòng hàng
CREATE TABLE brvsx_hoadonct (
    "Id"           bigint PRIMARY KEY,
    "CreatedAt"    timestamp,
    "ModifiedAt"   timestamp,
    "Stt"          text NOT NULL,                -- -> brvsx_hoadonhdr.Stt
    "RowId"        text NOT NULL,
    "ItemCode"     text,
    "Unit"         text,
    "Quantity"     double precision,
    "UnitPrice"    double precision,
    "Amount9"      double precision,
    "TaxCode"      text,
    "TaxRate"      double precision,
    "Amount3"      double precision,
    "DiscountRate" double precision,
    "Amount4"      double precision,
    "Reduce"       double precision,
    "CTKM"         text,
    "Quantity9"    double precision,
    "SyncAt"       timestamp,
    UNIQUE ("Stt", "RowId")
);

-- Hàng trả lại ETC — thêm 2026-07-07 qua scripts/sync_from_bravo_to_supabase.py (kéo trực
-- tiếp từ SQL Server thật DNH, KHÔNG nằm trong bản clone 6 tháng ban đầu). "Stt" là mã chứng
-- từ CỦA CHÍNH phiếu trả lại (dải số riêng), KHÔNG phải Stt hóa đơn gốc — xem ghi chú FK bên dưới.
-- DiscountRate/Amount4/Reduce ra kiểu "text" (khác brvsx_hoadonct cùng tên cột là double
-- precision) vì toàn bộ 39 dòng hiện tại NULL ở các cột này — pandas suy kiểu rỗng = text,
-- không phải lỗi ETL. Nếu cần đúng kiểu số, ALTER COLUMN TYPE khi có dữ liệu thật kiểm chứng.
CREATE TABLE brvsx_tralai (
    "Id"              bigint PRIMARY KEY,
    "BranchCode"      text,
    "DocGroup"        text,
    "DocNo"           text,
    "DocCode"         text,
    "Stt"             text NOT NULL,                -- mã chứng từ CỦA phiếu trả lại (không phải FK hdr)
    "TotalAmount0"    double precision,
    "CustomerCode"    text,                         -- -> dmssx_khachhang.Code (logic, không unique)
    "DocStatus"       bigint,
    "IsActive"        boolean,
    "DocDate"         text,
    "CreatedAt"       timestamp,
    "ModifiedAt"      timestamp,
    "RowId"           text NOT NULL,
    "ItemCode"        text,                         -- phần lớn KHÔNG khớp brv_sanpham (kênh ETC)
    "Unit"            text,
    "Quantity"        double precision,
    "UnitPrice"       double precision,
    "Amount9"         double precision,
    "TaxCode"         text,
    "TaxRate"         double precision,
    "Amount3"         double precision,
    "DiscountRate"    text,                         -- xem ghi chú kiểu dữ liệu ở trên
    "Amount4"         text,
    "Reduce"          text,
    "CTKM"            text,
    "Quantity9"       double precision,
    "DMSId"           text,
    "Description"     text,
    "CustomerCode0"   text,
    "DistributorCode" text,
    "EInvoice_Stt"    text,
    "EInvoice_RowId"  text,
    "SyncAt"          timestamp,
    "CustomerId"      bigint,
    "Account"         text,
    "CurrencyCode"    text,
    "ExchangeRate"    double precision,
    "MfgDate"         text,
    "ExpiryDate"      text,
    UNIQUE ("Stt", "RowId")
);

-- ============================================================
-- NHÓM DANH MỤC / DIMENSIONS
-- ============================================================

-- Khách hàng DMS (kênh OTC)
CREATE TABLE dms_khachhang (
    "Id"          bigint PRIMARY KEY,
    "Code"        text NOT NULL UNIQUE,          -- khóa join từ brv_hoadonhdr.CustomerCode
    "Name"        text,
    "CreatedAt"   timestamp,
    "ModifiedAt"  timestamp,
    "IsActive"    boolean,
    "SyncAt"      timestamp,
    "EmpDMSCode1" text,
    "LCH_FK"      double precision,
    "CityId"      bigint,                        -- -> dim_tinhthanhpho.CityId
    "DistrictId"  double precision,
    "StreetId"    double precision,
    "KenhBH"      text
);

-- Khách hàng DMS SX (kênh ETC)
CREATE TABLE dmssx_khachhang (
    "Id"         bigint PRIMARY KEY,
    "Code"       text NOT NULL,                  -- KHÔNG unique (1 mã trùng thực tế: 39.966/39.967)
    "Name"       text,
    "KenhBH"     text,
    "IsActive"   bigint,
    "LCH_FK"     double precision,
    "CityId"     bigint,                         -- -> dim_tinhthanhpho.CityId
    "DistrictId" double precision,
    "StreetId"   double precision,
    "CreatedAt"  timestamp,
    "ModifiedAt" text,
    "SyncAt"     timestamp
);

-- Sản phẩm Bravo
CREATE TABLE brv_sanpham (
    "Id"         bigint PRIMARY KEY,
    "Code"       text NOT NULL UNIQUE,           -- khóa join từ brv_hoadonct.ItemCode
    "Name"       text,
    "GroupCode"  text,
    "ReleaseAt"  text,
    "CreatedAt"  timestamp,
    "ModifiedAt" timestamp,
    "SyncAt"     timestamp,
    "IsActive"   bigint,
    "Unit"       text
);

-- Nhân viên
CREATE TABLE dim_nhanvien (
    "EmployeeCode"        text PRIMARY KEY,      -- đã kiểm chứng unique 306/306
    "DMSId"               text,                  -- KHÔNG unique (300/306)
    "Name"                text,
    "StartProbationDate"  text,
    "EndProbationDate"    text,
    "StartDate"           text,
    "EndDate"             text,
    "PositionCode"        text,
    "AreaCode"            text,
    "IsUsePhone"          double precision,
    "PhoneLimitAmount"    double precision,
    "AreaCode2"           text,
    "CityId"              double precision,
    "ManagerAreaCode"     text,
    "IsDuplicate"         double precision,
    "IsResigned"          text,
    "CallType"            double precision
);

-- Tỉnh/Thành phố
CREATE TABLE dim_tinhthanhpho (
    "CityId"         bigint PRIMARY KEY,
    "CityName"       text,
    "AreaCode"       text,
    "CallTarget"     double precision,
    "CallDayMin"     double precision,
    "CallDayMax"     double precision,
    "CallDayMinSat"  double precision,
    "CallDayMaxSat"  double precision,
    "AreaCode3"      text,
    "CallTarget2"    double precision,
    "CallDayMin2"    double precision,
    "CallDayMax2"    double precision,
    "CallDayMinSat2" double precision,
    "CallDayMaxSat2" double precision,
    "MNDetailCode"   text,
    "AreaCode2"      text,
    "CityCode"       text
);

-- Trạng thái duyệt chứng từ (dim trạng thái — lọc hủy)
CREATE TABLE brv_trangthaiduyet (
    "Id"                     bigint PRIMARY KEY,
    "ParentId"               bigint,
    "IsGroup"                boolean,
    "BuiltinOrder"           bigint,
    "DocStatusKey"           bigint NOT NULL UNIQUE,  -- khóa join từ brv_hoadonhdr.DocStatus
    "DocStatusName"          text,
    "DocStatusName_English"  text,
    "DocStatusName_French"   text,
    "DocStatusName_Japanese" text,
    "DocStatusName_Chinese"  text,
    "DocStatusName_Korean"   text,
    "DocStatusName_Custom"   text,
    "Ma_Nvu"                 text,
    "Nh_Ct"                  text,
    "Ma_Ct"                  text,
    "Post_SoCai"             boolean,
    "Post_TheKho"            boolean,
    "IsCancelled"            boolean,                 -- TRUE = chứng từ hủy, lọc khi tính doanh thu
    "Lock"                   boolean,
    "IsActive"               boolean
);

-- Trạng thái hóa đơn điện tử
CREATE TABLE brv_trangthaihoadon (
    "Id"                          bigint PRIMARY KEY,
    "ParentId"                    bigint,
    "IsGroup"                     boolean,
    "BuiltinOrder"                bigint,
    "EInvoiceStatusKey"           bigint NOT NULL UNIQUE,  -- khóa join từ brv_hoadonhdr.EInvoiceStatus
    "EInvoiceStatusName"          text,
    "EInvoiceStatusName_English"  text,
    "EInvoiceStatusName_French"   text,
    "EInvoiceStatusName_Japanese" text,
    "EInvoiceStatusName_Chinese"  text,
    "EInvoiceStatusName_Korean"   text,
    "EInvoiceStatusName_Custom"   text,
    "IsPublished"                 boolean,
    "IsCancelled"                 boolean,
    "IsActive"                    boolean,
    "CreatedBy"                   bigint,
    "CreatedAt"                   timestamp,
    "ModifiedBy"                  bigint,
    "ModifiedAt"                  timestamp,
    "timestamp"                   text
);

-- ============================================================
-- NHÓM MART (nguồn đọc trực tiếp của dashboard/alert)
-- ============================================================

-- Công nợ OTC theo kỳ + tuổi nợ (bucket aging)
CREATE TABLE receivable_detail (
    "id"            bigint PRIMARY KEY,
    "period"        text,                        -- kỳ báo cáo, vd '6_2026'
    "customer_code" text,                        -- -> dms_khachhang.Code (logic)
    "customer_name" text,
    "balance_end"   double precision,
    "in_term"       double precision,
    "overdue_1_15"  double precision,
    "overdue_15_30" double precision,
    "overdue_30_45" double precision,
    "overdue_gt_45" double precision,
    "total_overdue" double precision,
    "sales_channel" text
);

-- Tồn kho snapshot (hiện 1 dòng/item_code — đã kiểm chứng; nếu sau này tách
-- nhiều kho, đổi PK thành (item_code, warehouse))
CREATE TABLE inventory (
    "item_code"      text PRIMARY KEY,
    "item_name"      text,
    "unit"           text,
    "opening_qty"    double precision,
    "inward_qty"     double precision,
    "outward_qty"    double precision,
    "closing_qty"    double precision,
    "closing_value"  double precision,
    "months_to_sell" double precision,           -- >=12 tháng = tồn "chết" (dead stock alert)
    "warehouse"      text
);

-- KPI rollup theo nhân viên (tháng/quý/năm)
CREATE TABLE kpi_summary (
    "id"                    bigint PRIMARY KEY,
    "area_code"             text,
    "employee_code"         text UNIQUE,         -- -> dim_nhanvien.EmployeeCode (1-1, đã kiểm chứng)
    "employee_name"         text,
    "position_code"         text,
    "month_sale_target"     double precision,
    "month_sale_amount"     double precision,
    "month_sale_percent"    double precision,
    "total_point"           double precision,
    "quarter_sale_target"   double precision,
    "quarter_sale_amount"   double precision,
    "quarter_sale_percent"  double precision,
    "year_sale_target"      double precision,
    "year_sale_amount"      double precision,
    "year_sale_percent"     double precision
);

-- ============================================================
-- NHÓM VIEW VẬT CHẤT HÓA (snapshot của view production, header+detail đã gộp)
-- Không có PK tự nhiên (1 dòng = 1 dòng hàng đã denormalize) — chỉ index.
-- ============================================================

CREATE TABLE vw_hoadon_otc (
    "BranchCode" text, "DistributorCode" text, "Id" bigint, "RowId" text,
    "ItemCode" text, "Unit" text, "Quantity" double precision,
    "UnitPrice" double precision, "Amount9" double precision, "TaxCode" text,
    "TaxRate" double precision, "Amount3" double precision,
    "DiscountRate" double precision, "Amount4" double precision,
    "Reduce" double precision, "CTKM" text, "CreatedAt" text,
    "ModifiedAt" text, "SyncAt" text, "DocDate" text, "EmpDMSCode" text,
    "EmpDMSCode2" text, "CustomerCode" text, "Stt" text, "GroupCode" text,
    "DocCode" text, "DocNo" text, "DMSId" text, "CurEmpDMSCode" text,
    "CurEmpDMSCode2" text, "CustomerCode0" text, "CusDMSSeq" bigint,
    "CityId" bigint, "DistrictId" bigint, "StreetId" double precision
);

CREATE TABLE vw_hoadon_etc (
    "BranchCode" text, "DistributorCode" text, "Id" bigint, "RowId" text,
    "ItemCode" text, "Unit" text, "Quantity" double precision,
    "UnitPrice" double precision, "Amount9" double precision, "TaxCode" text,
    "TaxRate" double precision, "Amount3" double precision,
    "DiscountRate" double precision, "Amount4" double precision,
    "Reduce" double precision, "CTKM" text, "CreatedAt" text,
    "ModifiedAt" text, "SyncAt" text, "DocDate" text, "EmpDMSCode" text,
    "EmpDMSCode2" text, "CustomerCode" text, "Stt" text, "DocCode" text,
    "DocNo" text, "DMSId" text, "ContractId" bigint, "Description" text
);

-- ============================================================================
-- FOREIGN KEYS (quan hệ LOGIC mà code chatbot/alerts thực sự join — lớp hậu-ETL
-- gốc không có FK vật lý; thêm ở đây để vẽ sơ đồ + ép toàn vẹn trên dev)
-- ============================================================================

-- Đã ANTI-JOIN kiểm chứng số dòng mồ côi thật trên dev cho MỌI FK dưới đây trước khi
-- viết constraint (không suy đoán). FK nào có dòng mồ côi dùng NOT VALID để tạo được
-- (không lỗi khi chạy thật) nhưng KHÔNG validate ngược dữ liệu cũ — vẫn vẽ được quan hệ.

-- Header -> Detail (1-n) — 0 dòng mồ côi, FK sạch 100%
ALTER TABLE brv_hoadonct   ADD CONSTRAINT fk_brvct_hdr   FOREIGN KEY ("Stt") REFERENCES brv_hoadonhdr ("Stt");
ALTER TABLE brvsx_hoadonct ADD CONSTRAINT fk_brvsxct_hdr FOREIGN KEY ("Stt") REFERENCES brvsx_hoadonhdr ("Stt");

-- Hóa đơn OTC -> Khách hàng: 80/25.557 dòng mồ côi — ĐÃ BIẾT NGUYÊN NHÂN (không phải lỗi):
-- đây là các mã nội bộ dùng cho chuyển kho giữa chi nhánh (vd '1001136','1001679','P000001',
-- 'P000002'...), cố ý không có trong dim khách hàng — hệ thống chatbot join INNER với
-- dms_khachhang chính là để tự động loại các mã này khi tính doanh thu thật.
ALTER TABLE brv_hoadonhdr ADD CONSTRAINT fk_brvhdr_kh FOREIGN KEY ("CustomerCode")
    REFERENCES dms_khachhang ("Code") NOT VALID;

-- Hóa đơn ETC -> Khách hàng ETC: 182/2.448 dòng mồ côi (cùng lý do mã nội bộ như trên) —
-- KHÔNG tạo constraint được: dmssx_khachhang."Code" không unique (1 mã trùng thực tế,
-- 39.966/39.967), Postgres bắt buộc cột đích FK phải có UNIQUE/PK. Chỉ vẽ quan hệ logic
-- (nét đứt) khi dựng sơ đồ, không ép constraint.

-- Chi tiết OTC -> Sản phẩm: 0 dòng mồ côi, FK sạch 100%
ALTER TABLE brv_hoadonct ADD CONSTRAINT fk_brvct_sp FOREIGN KEY ("ItemCode") REFERENCES brv_sanpham ("Code");

-- Chi tiết ETC -> Sản phẩm: 1.629/9.919 dòng mồ côi (~16%) — brv_sanpham là danh mục sản
-- phẩm của kênh Bravo OTC; kênh ETC (Bravo SX) rõ ràng bán một số mã hàng KHÔNG có trong
-- danh mục này (chưa xác định có danh mục sản phẩm ETC riêng hay không) — GHI CHÚ RÕ, KHÔNG
-- áp constraint cứng, chỉ vẽ đường nối logic (nét đứt) khi dựng sơ đồ.

-- brvsx_tralai: đã thử cả 3 quan hệ logic có vẻ hợp lý theo tên cột, CẢ 3 đều KHÔNG tạo FK được
-- (đã anti-join kiểm chứng thật, không suy đoán):
--   · Stt -> brvsx_hoadonhdr.Stt: 39/39 mồ côi (100%) — phiếu trả lại có dải số chứng từ RIÊNG,
--     không dùng lại Stt hóa đơn gốc. Không phải lỗi dữ liệu, chỉ là không có quan hệ này.
--   · ItemCode -> brv_sanpham.Code: 26/39 mồ côi (~67%) — cùng nguyên nhân danh mục OTC/ETC
--     tách biệt đã ghi chú ở trên cho brvsx_hoadonct.
--   · CustomerCode -> dmssx_khachhang.Code: chỉ 2/39 mồ côi (~5%, khá sạch) NHƯNG vẫn không
--     tạo được constraint vì dmssx_khachhang."Code" không unique (xem ghi chú Hóa đơn ETC ở
--     trên) — Postgres bắt buộc cột đích FK phải có UNIQUE/PK bất kể NOT VALID.

-- Hóa đơn -> Dim trạng thái: 0 dòng mồ côi cả 2, FK sạch 100%
ALTER TABLE brv_hoadonhdr ADD CONSTRAINT fk_brvhdr_tthd FOREIGN KEY ("EInvoiceStatus") REFERENCES brv_trangthaihoadon ("EInvoiceStatusKey");
ALTER TABLE brv_hoadonhdr ADD CONSTRAINT fk_brvhdr_ttd  FOREIGN KEY ("DocStatus") REFERENCES brv_trangthaiduyet ("DocStatusKey");

-- Khách hàng -> Tỉnh/Thành: 0 dòng mồ côi cả 2, FK sạch 100%
ALTER TABLE dms_khachhang   ADD CONSTRAINT fk_dmskh_city   FOREIGN KEY ("CityId") REFERENCES dim_tinhthanhpho ("CityId");
ALTER TABLE dmssx_khachhang ADD CONSTRAINT fk_dmssxkh_city FOREIGN KEY ("CityId") REFERENCES dim_tinhthanhpho ("CityId");

-- KPI -> Nhân viên (1-1): 1/58 dòng mồ côi (1 employee_code lẻ không có trong dim_nhanvien,
-- có thể nhân sự đã nghỉ/mã cũ) — dùng NOT VALID để không chặn 57 dòng còn lại.
ALTER TABLE kpi_summary ADD CONSTRAINT fk_kpi_nv FOREIGN KEY ("employee_code")
    REFERENCES dim_nhanvien ("EmployeeCode") NOT VALID;

-- Công nợ -> Khách hàng: 2.014/165.102 dòng mồ côi (~1,2%) — receivable_detail gộp CẢ 2
-- kênh (cột sales_channel = 'OTC'/'ETC'), nên customer_code là KHÔNG GIAN MÃ HỖN HỢP của
-- dms_khachhang (OTC) VÀ dmssx_khachhang (ETC) cùng lúc — một FK đơn sang 1 bảng chắc chắn
-- sai thiết kế (không phải lỗi dữ liệu). KHÔNG tạo constraint; khi vẽ sơ đồ, nối 2 đường
-- logic riêng: receivable_detail (WHERE sales_channel='OTC') -> dms_khachhang, và
-- receivable_detail (WHERE sales_channel='ETC') -> dmssx_khachhang.

-- ============================================================================
-- INDEXES (khớp production + bổ sung DocDate mà production đang thiếu)
-- Ghi chú: các cột PRIMARY KEY/UNIQUE đã tự có index, không lặp lại.
-- ============================================================================

-- brv_hoadonhdr: production có index CustomerCode + Stt; DocDate bổ sung mới
CREATE INDEX idx_brvhdr_customer ON brv_hoadonhdr ("CustomerCode");
CREATE INDEX idx_brvhdr_docdate  ON brv_hoadonhdr ("DocDate");     -- lọc theo tháng (alert/chatbot)
CREATE INDEX idx_brvhdr_syncat   ON brv_hoadonhdr ("SyncAt");      -- watermark ETL freshness

-- brv_hoadonct: production có index ItemCode + Stt (Stt đã nằm trong UNIQUE(Stt,RowId) - dùng được prefix)
CREATE INDEX idx_brvct_item      ON brv_hoadonct ("ItemCode");

-- brvsx_hoadonhdr: production có index CustomerCode
CREATE INDEX idx_brvsxhdr_customer ON brvsx_hoadonhdr ("CustomerCode");
CREATE INDEX idx_brvsxhdr_docdate  ON brvsx_hoadonhdr ("DocDate");

-- brvsx_hoadonct: production có index ItemCode + Stt
CREATE INDEX idx_brvsxct_item    ON brvsx_hoadonct ("ItemCode");

-- brvsx_tralai: bảng mới (2026-07-07) — index theo đúng pattern các cột hay lọc/join của bảng chị em
CREATE INDEX idx_tralai_customer ON brvsx_tralai ("CustomerCode");
CREATE INDEX idx_tralai_item     ON brvsx_tralai ("ItemCode");
CREATE INDEX idx_tralai_docdate  ON brvsx_tralai ("DocDate");

-- dms_khachhang: production có index Code (đã thành UNIQUE ở trên) + CityId
CREATE INDEX idx_dmskh_city      ON dms_khachhang ("CityId");

-- dmssx_khachhang: production có index Code (không unique được — xem ghi chú trên)
CREATE INDEX idx_dmssxkh_code    ON dmssx_khachhang ("Code");
CREATE INDEX idx_dmssxkh_city    ON dmssx_khachhang ("CityId");

-- receivable_detail: production có idx_receivable_detail_period (thêm sống 2026-07)
CREATE INDEX idx_rec_period      ON receivable_detail ("period");
CREATE INDEX idx_rec_customer    ON receivable_detail ("customer_code");

-- View vật chất hóa: index theo pattern join/lọc của chatbot
CREATE INDEX idx_vwotc_stt       ON vw_hoadon_otc ("Stt");
CREATE INDEX idx_vwotc_customer  ON vw_hoadon_otc ("CustomerCode");
CREATE INDEX idx_vwotc_item      ON vw_hoadon_otc ("ItemCode");
CREATE INDEX idx_vwotc_docdate   ON vw_hoadon_otc ("DocDate");
CREATE INDEX idx_vwetc_stt       ON vw_hoadon_etc ("Stt");
CREATE INDEX idx_vwetc_customer  ON vw_hoadon_etc ("CustomerCode");
CREATE INDEX idx_vwetc_item      ON vw_hoadon_etc ("ItemCode");
CREATE INDEX idx_vwetc_docdate   ON vw_hoadon_etc ("DocDate");
