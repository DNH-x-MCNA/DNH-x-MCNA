# -*- coding: utf-8 -*-
"""
Mo ta schema du lieu DNH cho AI hieu de sinh SQL dung.

NGUON DU LIEU (tu 2026-07-08):
- "local" (SQLite, file warehouse.db) la kho CHINH cho HAU HET cau hoi - duoc dong bo dinh ky
  (moi 15-30 phut) tu Bravo qua sync_warehouse.py, co INDEX + DAY DU LICH SU NHIEU NAM, tra loi
  nhanh (<=10s). Dung tool query_database cho cau hoi tu do ve doanh thu/san pham/khach hang/
  nhan vien/vung mien/tra hang khong thuoc 5 tool bao cao chuan.
- Supabase CHI con dung cho inventory/receivable_detail/receivable_etc (bang do dong nghiep tu
  nhap, Bravo KHONG CO nguon tuong duong) - dung tool query_inventory_receivables.
- Bravo (SQL Server song, may chu that cua khach hang) KHONG con duoc chatbot goi truc tiep nua -
  chi co job dong bo nen moi cham toi, giup chatbot khong phu thuoc VPN on dinh moi luc.
!!! Du lieu "local" co the tre toi da ~15-30 phut so voi Bravo that - neu nguoi dung hoi so lieu
"vua moi/ngay bay gio", noi ro day la so lieu tai lan dong bo gan nhat, khong phai tuc thoi 100%.
"""

SCHEMA_CONTEXT = """
=== KHO "local" (SQLite) - dung voi tool query_database. Ten bang/cot deu chu thuong, KHONG can
dat trong dau ngoac kep (SQLite khong phan biet hoa/thuong nhu Postgres). Dung LIMIT N (khong dung
TOP N cua T-SQL). Ham ngay thang: date(), julianday() - cot doc_date/save_date la dang text 'YYYY-MM-DD'. ===

vhoadon_otc (moi dong la 1 dong hoa don chi tiet, kenh OTC - nha thuoc/nha phan phoi):
  doc_date (text 'YYYY-MM-DD', so sanh truc tiep vd doc_date BETWEEN '2026-07-01' AND '2026-07-03'),
  customer_code, item_code, amount9 (doanh thu - dung SUM(amount9) de tinh doanh thu),
  quantity, unit_price (=0 la hang khuyen mai/tang, loai khoi so luong ban that khi tinh Top SP),
  stt (ma chung tu, dung COUNT(DISTINCT stt) de dem so hoa don), city_id (CO TREN BANG NHUNG KHONG
  DANG TIN - DA ben Bravo da xac nhan truong nay hay bi sai/thieu so voi vung thuc te cua khach hang.
  TUYET DOI KHONG dung truc tiep de loc/nhom theo vung mien - da tung gay lech doanh thu ~18 ty/6
  thang cho 1 vung. Muon biet vung mien PHAI JOIN qua customer_code -> dms_khachhang.code -> city_id,
  giong het cach lam voi ETC ben duoi),
  employee_code (ma NHAN VIEN BAN HANG CA NHAN gan voi hoa don nay, vd 'tungtx' - CHI co gia tri cho
  nhan vien ca nhan, ma khu vuc/quan ly vung nhu MBKV*/ASM* KHONG xuat hien o day),
  created_at (text 'YYYY-MM-DD HH:MM:SS' - thoi diem BAN GHI THUC SU duoc tao trong Bravo, KHAC voi
  doc_date la ngay chung tu ghi tren hoa don (co the bi chon tay/backdate). So sanh 2 cot nay de phat
  hien "chay don don KPI" - xem tool check_order_timing).

vhoadon_etc: doanh thu kenh ETC (benh vien). Cau truc GIONG vhoadon_otc (cung KHONG dung city_id
  rieng cua hoa don) - muon biet vung mien phai JOIN qua customer_code -> dmssx_khachhang.code -> city_id.

dim_tinhthanhpho: city_id, city_name, area_code (MB=Mien Bac, MT=Mien Trung, MN=Mien Nam).
dim_targetvungmien: target doanh thu OTC theo vung/thang. Cot: area_code, channel_code (loc ='GT'
  cho kenh OTC), amount (target tien), doc_date (ngay dau thang, vd '2026-06-01' cho target thang 6).
fact_kehoachtongetc: target tong ETC theo thang. Cot: doc_date (ngay dau thang), amount, item_group.
dmssx_khachhang: code (ma khach hang ETC), name, city_id (dung join vung mien cho ETC), id_code (Id
  noi bo DMS, khac code), kenh_bh (kenh ban hang dang text). KHONG co cot NV phu trach (ETC khong co
  truong nay tren Bravo - chi biet NV thuc te ban hang qua vhoadon_etc.employee_code).
dms_khachhang: code (ma khach hang OTC), name, city_id (NGUON DUNG DE XAC DINH VUNG MIEN cho OTC -
  dang tin cay hon city_id tren vhoadon_otc, xem ghi chu o vhoadon_otc phia tren),
  id_code (Id noi bo DMS, khac code), emp_code (ma NV DUOC GAN phu trach khach hang nay - khac
  vhoadon_otc.employee_code la NV THUC TE ban hang tren tung hoa don, 2 ma co the khac nhau), kenh_bh.

dim_nhanvien: employee_code, name, is_duplicate (=1 la ma bi trung/khong hop le,
  LUON loc COALESCE(is_duplicate,0)<>1 O MENH DE WHERE - KHONG dat dieu kien nay trong ON cua
  LEFT JOIN, vi se khong loai duoc dong du lieu, chi mat ten - da tung gay bug that), position_code
  (TDV/QLV/CTV/CS/TP/PP/TBP/TK - LUU Y: 1 nhan vien co the la QLV du EmployeeCode "nhin giong" ten
  ca nhan, KHONG suy doan vai tro tu ten ma phai kiem tra position_code), area_code (MB/MT/MN).
dim_chucvu: position_code, description (ten tieng Viet day du, vd TDV -> "Trinh duoc vien", QLV ->
  "Quan ly vung" - JOIN qua position_code de hien thi ten vai tro dep, DISTINCT san khi dong bo).
fact_tonghopkhachhang: 1 dong = 1 (nhan vien, khach hang, ngay snapshot). Cot: employee_code,
  customer_code, amount_ct (doanh so NV voi KH do - SUM de ra doanh so NV), month_sale_target (target
  thang, MAX vi lap lai moi dong), save_date (ngay snapshot - dung MAX(save_date) <= ngay can xem de
  lay snapshot gan nhat), is_nc (=1 neu la KH moi trong thang). CHI CO ~90 NGAY GAN NHAT trong kho
  local (lich su xa hon khong dong bo vi it gia tri cho KPI hien tai).
  NGUONG DAT KPI nhan vien la >=80% (amount_ct/month_sale_target), KHONG PHAI 100%.

brv_sanpham: code, name, group_code (nhom SP), unit (don vi tinh).

brvsx_tralai: tra hang (CHI co kenh ETC, OTC chua co nguon). Cot: doc_date, amount9 (gia tri tra),
  is_active (=1 la hop le), stt (ma chung tu), customer_code.

=== SUPABASE (PostgreSQL) - CHI dung voi tool query_inventory_receivables ===
(Ten cot phan biet hoa/thuong, PHAI dat trong dau ngoac kep "...", dung LIMIT N)

inventory (snapshot ton kho MOI NHAT, khong theo ngay): "item_code", "item_name", "unit",
  "opening_qty", "inward_qty", "outward_qty", "closing_qty" (ton cuoi SL),
  "closing_value" (ton cuoi tien), "months_to_sell" (so thang uoc tinh ban het ton hien tai -
  CANG THAP ban cang nhanh, <=1 la sap can xu ly/ban rat cham), "warehouse".

receivable_detail: cong no kenh OTC/chung, theo tung ky (thang). Cot: "period" (dang "thang_nam"
  vd "9_2025"), "customer_code", "customer_name", "balance_end" (du no cuoi ky), "in_term",
  "overdue_1_15","overdue_15_30","overdue_30_45","overdue_gt_45", "total_overdue", "sales_channel".
  LUU Y: chi co toi ky gan nhat hien co (dung MAX de tim ky moi nhat, KHONG gia dinh la thang hien tai).
receivable_etc: cong no kenh ETC. Cot: "customer_code", "customer_name", "contract_value",
  "total_paid", "in_term", "overdue_1_7","overdue_8_14","overdue_15_21","overdue_gt_21",
  "total_overdue", "total_receivable", "province_code", "sales_manager". KHONG co cot "period"
  (la snapshot hien tai, khong chia theo ky).

=== QUY TAC QUAN TRONG ===
1. Doanh thu = SUM(amount9), KHONG dung cot nao khac.
2. Neu can "ngay gan nhat"/"hom nay" ma khong ro ngay cu the, dung MAX(doc_date) tu vhoadon_otc
   de tim ngay moi nhat CO DU LIEU trong kho local (co the tre vai chuc phut so voi Bravo that).
3. Khi tinh Top san pham/khach hang, LUON loai hang khuyen mai (loc unit_price > 0 cho so luong).
4. Khi JOIN dim_nhanvien, LUON loc COALESCE(is_duplicate,0)<>1 O MENH DE WHERE (khong phai ON).
4b. BAT BUOC: neu cau SELECT co employee_code (vd tren vhoadon_otc/etc, dms_khachhang.emp_code...),
   LUON LEFT JOIN dim_nhanvien de lay them ten (nv.name) va vai tro (LEFT JOIN dim_chucvu de lay
   position_label) - TUYET DOI KHONG tra ve/hien thi ma nhan vien tran (vd "tungtx") ma khong kem ten,
   nguoi dung khong nho duoc ma nao la ai.
5. CHI duoc sinh cau lenh SELECT (hoac WITH ... SELECT). TUYET DOI KHONG sinh INSERT/UPDATE/DELETE/
   DROP/ALTER/TRUNCATE.
6. Neu cau hoi mo ho/thieu thong tin, hay hoi lai nguoi dung thay vi doan bua.
7. Luon tra loi bang TIENG VIET, ro rang, ngan gon, co so lieu cu the kem don vi (ty/trieu dong).
8. Neu cau hoi co NHIEU khia canh (vd hoi ca theo san pham, khach hang, vung mien, nhan vien cung
   luc), hay tach thanh cac truy van rieng biet tuan tu, KHONG co gang gop tat ca vao 1 cau SQL qua phuc tap.
9. query_database chay tren kho "local" (SQLite - LIMIT N, khong quote ten cot). query_inventory_receivables
   chay tren SUPABASE (PostgreSQL - quote ten cot trong "...", LIMIT N). KHONG dung nham dialect giua 2 tool.
10. Kho local co DAY DU LICH SU nhieu nam (tu ~2022) nen thoai mai so sanh xa (nam nay vs nam truoc,
    quy nay vs quy truoc...) - dung tool compare_periods hoac tu ghep 2 lan goi get_revenue_by_channel.
"""
