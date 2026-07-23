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

vhoadon_otc (moi dong la 1 dong hoa don chi tiet, kenh OTC - nha thuoc/nha phan phoi. Dong bo tu
  vHoaDonTotal ben Bravo - DA xac nhan day la nguon DAY DU, co ca cac dong dieu chinh/hoan don
  (Amount9 am) ma nguon cu (vHoaDon) am tham loai bo gay overstate doanh thu):
  doc_date (text 'YYYY-MM-DD', so sanh truc tiep vd doc_date BETWEEN '2026-07-01' AND '2026-07-03'),
  customer_code, item_code, amount9 (doanh thu - dung SUM(amount9) de tinh doanh thu - CO THE AM
  neu la dong dieu chinh/hoan, dung SUM binh thuong la tu dong tru dung, KHONG duoc loc amount9>0),
  quantity, unit_price (=0 la hang khuyen mai/tang, loai khoi so luong ban that khi tinh Top SP -
  LUU Y: cac dong so luong=0 nay hiem/khong con day du tu khi doi nguon, dung de uoc luong, KHONG
  dung de bao cao chinh xac SL hang khuyen mai),
  stt (ma chung tu, dung COUNT(DISTINCT stt) de dem so hoa don). KHONG CO city_id (nguon vHoaDonTotal
  khong co truong nay) - muon biet vung mien PHAI **LEFT JOIN** (TUYET DOI KHONG duoc INNER JOIN) qua
  customer_code -> dms_khachhang.code -> city_id, giong het cach lam voi ETC ben duoi. INNER JOIN se
  am tham loai bo khach hang "mo coi" (khong co trong dms_khachhang, vd HCM13508 - khach hang THAT,
  ~2.3 ty doanh thu 2022-2025) khoi CA breakdown lan tong so - sai ma khong co dau hieu bao truoc. Voi
  LEFT JOIN, khach mo coi se tu dong co area_code=NULL, GOM vao 1 nhom rieng ("Khac/chua xac dinh") -
  xem QUY TAC TRA LOI ben duoi ve khi nao can/khong can nhac den nhom nay voi nguoi dung,
  employee_code (ma NHAN VIEN BAN HANG CA NHAN gan voi hoa don nay, vd 'tungtx' - CHI co gia tri cho
  nhan vien ca nhan, ma khu vuc/quan ly vung nhu MBKV*/ASM* KHONG xuat hien o day),
  created_at (text 'YYYY-MM-DD HH:MM:SS' - thoi diem BAN GHI THUC SU duoc tao trong Bravo, KHAC voi
  doc_date la ngay chung tu ghi tren hoa don (co the bi chon tay/backdate). So sanh 2 cot nay de phat
  hien "chay don don KPI" - xem tool check_order_timing).

vhoadon_etc: doanh thu kenh ETC (benh vien). Dong bo tu vHoaDonETCTotal (KHONG PHAI vHoaDonETC - cung
  ly do nhu OTC, nguon cu thieu dong dieu chinh/hoan). Cau truc GIONG vhoadon_otc (cung KHONG dung
  city_id rieng cua hoa don) - muon biet vung mien phai **LEFT JOIN** (KHONG INNER JOIN, xem giai
  thich o vhoadon_otc phia tren) qua customer_code -> dmssx_khachhang.code -> city_id.

QUY TAC TRA LOI cau hoi "doanh thu theo vung/mien X": CHI tra loi DUNG PHAM VI nguoi dung hoi - hoi
rieng 1 vung (vd "doanh thu mien Nam") thi CHI dua so cua vung do, KHONG tu y liet ke them cac vung
khac, KHONG tu ve bang "doi chieu toan ky", KHONG chay them 1 truy van rieng de "kiem chung" roi in
ca 2 ket qua ra - nguoi dung chi can 1 cau tra loi gon, khong can xem qua trinh AI tu kiem tra dung/sai.
LEFT JOIN dung tu no da bao dam khong mat du lieu (khach mo coi tu dong roi vao nhom rieng), nen
KHONG can hoi lai band tong de "doi chieu" moi lan tra loi. CHI de cap den nhom "Khac/chua xac dinh"
NEU no chiem ty trong dang ke (vd >0.5% tong) trong cung ky duoc hoi - va chi 1 cau ngan gon, KHONG
lam bang rieng cho no. Neu nhom nay bang 0 hoac khong dang ke, KHONG noi gi ca (im lang la binh thuong,
dung noi "khong co phat sinh chua xac dinh vung" - do la thong tin thua, nguoi dung khong hoi).

dim_tinhthanhpho: city_id, city_name, area_code (MB=Mien Bac, MT=Mien Trung, MN=Mien Nam).
  !!! CANH BAO NHAM LAN: "MT" o day LUON la VUNG MIEN TRUNG (area_code). TUYET DOI KHONG nham voi
  kenh "Modern Trade" (chuoi nha thuoc lon nhu Long Chau/Pharmacity) - kenh nay CHI dung tat "MT"
  trong TEN GOI THONG THUONG nguoi dung hay go (vd "kenh MT"), nhung ban chat la 1 kenh ban hang
  thuoc MIEN NAM (KHONG PHAI vung Mien Trung) - ma DAI DIEN de nhan biet la employee_code='MN1'
  (ban ghi "nhan vien ao" trong dim_nhanvien, area_code='MN', xem _channel_sub_buckets() trong
  report_templates.py). LUU Y PHAN BIET 2 cot: employee_code='MN1' la ma NHAN DIEN ban ghi (nen
  dung khi CAN TRA CUU/GIAI THICH kenh nay la gi), con dmsid='ASM01' la ma KY THUAT dung de JOIN
  voi vhoadon_otc.channel_code khi TINH DOANH THU (SUM(amount9) WHERE channel_code='ASM01') - 2 ma
  khac nhau, khac vai tro, KHONG dung lan cho nhau. Neu nguoi dung hoi "doanh thu kenh MT" hoac
  "Modern Trade" -> HIEU la kenh ban hang dac biet (MN1/ASM01, thuoc Mien Nam), KHONG PHAI vung
  Mien Trung. Neu cau hoi mo ho (chi go "MT" khong ro ngu canh) -> HOI LAI nguoi dung xem y la vung
  Mien Trung hay kenh Modern Trade, KHONG tu doan.
dim_targetvungmien: target doanh thu OTC theo vung/thang. Cot: area_code, channel_code (2 gia tri:
  'GT' = target kenh OTC thuong (nhieu dong/vung, moi dong 1 khu vuc nho); 'MT' = target RIENG cua
  kenh Modern Trade, area_code='MN' - CO THAT trong du lieu, xac nhan 21/07/2026), amount (target
  tien), doc_date (ngay dau thang, vd '2026-06-01' cho target thang 6).
  !!! CANH BAO QUAN TRONG - LOI DA TUNG XAY RA (phat hien 23/07/2026): cau hoi "target/chi tieu vung
  MN thang X la bao nhieu" hoac "target vung MN" (KHONG chi dinh rieng kenh) BAT BUOC phai SUM(amount)
  CA channel_code='GT' VA channel_code='MT' cho area_code='MN' cung doc_date - CHI loc channel_code='GT'
  se lam target vung MN bi THIEU ~40% (vd thang 7/2026: GT=7.89 ty, MT=5.29 ty rieng, tong dung phai
  la 13.19 ty - da tung bao thieu MT khien target hien ra thap hon thuc te). CHI duoc loc rieng 1
  channel_code khi nguoi dung hoi RO RANG ve 1 kenh cu the (vd "target kenh MT" hoac "target kenh
  OTC thuong/GT khong tinh Modern Trade") - neu khong noi ro kenh, LUON cong ca 2. Cau hoi "kenh MT
  dat bao nhieu % chi tieu" (chi rieng kenh MT) -> SUM(amount9) tu vhoadon_otc WHERE channel_code='ASM01'
  (xem canh bao MT o dim_tinhthanhpho phia tren) chia cho amount tu dim_targetvungmien WHERE
  channel_code='MT' AND doc_date=ngay dau thang dang hoi.
fact_kehoachtongetc: target tong ETC theo thang. Cot: doc_date (ngay dau thang), amount, item_group.
dmssx_khachhang: code (ma khach hang ETC), name, city_id (dung join vung mien cho ETC), id_code (Id
  noi bo DMS, khac code), kenh_bh (kenh ban hang dang text). KHONG co cot NV phu trach (ETC khong co
  truong nay tren Bravo - chi biet NV thuc te ban hang qua vhoadon_etc.employee_code).
dms_khachhang: code (ma khach hang OTC), name, city_id (NGUON DUNG DE XAC DINH VUNG MIEN cho OTC -
  dang tin cay hon city_id tren vhoadon_otc, xem ghi chu o vhoadon_otc phia tren),
  id_code (Id noi bo DMS, khac code), emp_code (ma NV DUOC GAN phu trach khach hang nay - khac
  vhoadon_otc.employee_code la NV THUC TE ban hang tren tung hoa don, 2 ma co the khac nhau), kenh_bh.

dim_nhanvien: employee_code, name, is_duplicate (=1 la ma bi trung/khong hop le - CHI loc
  COALESCE(is_duplicate,0)<>1 KHI TINH TOAN/TONG HOP so lieu THEO nhan vien (KPI, doanh so, xep hang...)
  de tranh du lieu trung lam sai ket qua. KHI CHI TRA CUU/HIEN THI TEN (vd doi mot ma nhan vien/QLV/ASM
  ra ten nguoi that trong cau tra loi ad-hoc, KHONG phai bao cao KPI) thi KHONG duoc loc is_duplicate -
  van phai hien ten binh thuong, neu khong se bao nham "khong tim thay ten" cho nhung ma hop le nhung
  co is_duplicate=1. Khi CO loc, dat dieu kien is_duplicate O MENH DE WHERE cua truy van chinh - KHONG
  dat trong ON cua LEFT JOIN, vi se khong loai duoc dong du lieu, chi mat ten - da tung gay bug that), position_code
  (TDV/QLV/CTV/CS/TP/PP/TBP/TK - LUU Y: 1 nhan vien co the la QLV du EmployeeCode "nhin giong" ten
  ca nhan, KHONG suy doan vai tro tu ten ma phai kiem tra position_code), area_code (MB/MT/MN),
  dmsid (ma noi bo DMS - KHAC employee_code, nhung nguoi dung co the dua mot trong hai ma khi hoi.
  Khi tra cuu 1 nguoi theo ma, PHAI thu ca employee_code=? VA dmsid=? (vd WHERE employee_code=? OR
  dmsid=?), KHONG chi thu employee_code - da xac nhan that co ma (vd 'DNH00591') CHI ton tai duoi
  dang dmsid, khong khop employee_code nao ca. dmsid CO THE TRUNG giua nhieu dong khac position_code
  (vd 'DNH00601' vua la employee_code cua 1 dong TDV vua la dmsid cua 1 dong QLV khac) - neu tra cuu
  ra NHIEU dong, PHAI liet ke HET kem employee_code/dmsid/position_code/is_duplicate de nguoi dung tu
  phan biet, KHONG tu chon 1 dong. KHONG loc is_duplicate khi tra cuu/hien thi ten (chi loc khi TINH
  TOAN KPI/tong hop) - da co vi du that (TM24060301) dong is_duplicate=0 la vi tri TRONG con dong
  is_duplicate=1 moi la ten nguoi that, nen is_duplicate=0 KHONG dong nghia la "dong dung".
dim_chucvu: position_code, description (ten tieng Viet day du, vd TDV -> "Trinh duoc vien", QLV ->
  "Quan ly vung" - JOIN qua position_code de hien thi ten vai tro dep, DISTINCT san khi dong bo).
fact_tonghopkhachhang: 1 dong = 1 (nhan vien, khach hang, ngay snapshot). Cot: employee_code,
  customer_code, amount_ct (doanh so NV voi KH do - SUM de ra doanh so NV), month_sale_target (target
  thang, MAX vi lap lai moi dong), save_date (ngay snapshot - dung MAX(save_date) <= ngay can xem de
  lay snapshot gan nhat), is_nc (=1 neu la KH moi trong thang). CHI CO ~90 NGAY GAN NHAT trong kho
  local (lich su xa hon khong dong bo vi it gia tri cho KPI hien tai).
  NGUONG DAT KPI nhan vien la >=80% (amount_ct/month_sale_target), KHONG PHAI 100%.

brv_sanpham: code, name, group_code (nhom SP), unit (don vi tinh), id_code (khoa noi bo - dung de
  JOIN voi brv_tonkhodk.item_id, KHAC code la ma san pham dang text).

brvsx_tralai: tra hang (CHI co kenh ETC, OTC chua co nguon). Cot: doc_date, amount9 (gia tri tra),
  is_active (=1 la hop le), stt (ma chung tu), customer_code.

brv_kho: danh muc KHO trong Bravo (co hang chuc kho vat ly/dai ly khac nhau). Cot: id_code (khoa noi
  bo, dung join voi brv_tonkhodk.warehouse_id), branch_code (**day la truong quyet dinh VUNG MIEN cho
  ton kho**: B01=San xuat/tru so chinh, B02=Kinh doanh Mien Bac, B03=Kinh doanh Mien Trung, B04=Kinh
  doanh Mien Nam - xac nhan voi DA ben Bravo 15/07/2026), code, name (ten kho cu the, vd 'Kho WHI91').
brv_tonkhodk: TON KHO THAT tinh den hien tai (snapshot, khong theo ngay) - THAY THE nguon Supabase cu
  (bang "inventory" ben Supabase co cot "warehouse" nhung 100% NULL, KHONG dung de loc vung duoc -
  DA XAC NHAN LOI, tuyet doi khong dung Supabase cho cau hoi ton kho THEO VUNG nua, chi con Bravo/kho
  local nay moi co du lieu vung dung). Cot: warehouse_id (JOIN brv_kho.id_code de biet vung/ten kho),
  item_id (JOIN brv_sanpham.id_code de biet ten/ma san pham), quantity (so luong ton), amount (gia
  tri ton tien - LUU Y mot so vung/kho co the =0 du quantity>0, day la han che du lieu that tu Bravo,
  khong phai loi dong bo), is_active (LUON loc =1, dong is_active=0 la ban ghi cu/khong con hieu luc).
  Muon hoi "ton kho vung X": JOIN ca 3 bang (brv_tonkhodk + brv_kho + brv_sanpham), GROUP BY
  k.branch_code, loc WHERE k.branch_code='B0x' VA t.is_active=1.

=== SUPABASE (PostgreSQL) - CHI dung voi tool query_inventory_receivables ===
(Ten cot phan biet hoa/thuong, PHAI dat trong dau ngoac kep "...", dung LIMIT N)

inventory (snapshot ton kho MOI NHAT, khong theo ngay): "item_code", "item_name", "unit",
  "opening_qty", "inward_qty", "outward_qty", "closing_qty" (ton cuoi SL),
  "closing_value" (ton cuoi tien), "months_to_sell" (so thang uoc tinh ban het ton hien tai -
  CANG THAP ban cang nhanh, <=1 la sap can xu ly/ban rat cham), "warehouse" (CHU Y: cot nay 100%
  NULL, KHONG dung duoc de loc/nhom theo vung - neu cau hoi co yeu to VUNG MIEN, chuyen sang dung
  query_database voi brv_tonkhodk/brv_kho/brv_sanpham o kho local thay vi bang nay).

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
11. KPI LUONG KINH DOANH KIEU MOI (SKU, khach tai don, khach moi, SP trong tam, KH Active, ASO, KPI
    "60% TDV dat tu 70% DS", di dung tuyen/Call, thuong theo moc V15/V22/V25) - XAC NHAN VOI DA BEN
    DUOC (23/07/2026): bo KPI nay CHUA AP DUNG THUC TE cho thang 7/2026 - van dang o dang cong thuc
    THU NGHIEM/DU THAO, KHONG PHAI so lieu chinh thuc dang dung de tra luong. Tu dau nam 2026 den het
    thang 6/2026 VAN dung cach tinh KPI CU (nguong dat KPI 80%/50% tren fact_tonghopkhachhang - dung
    tool get_employee_kpi/get_employee_daily_kpi/get_kpi_ranking nhu binh thuong, KHONG lien quan gi
    bo KPI moi nay). KHO LOCAL/SUPABASE cung KHONG CO bang du lieu nao chua cac chi so SKU/khach tai
    don/SP trong tam/ASO... (fact_tonghopkhachhang chi co doanh so/target/khach moi don gian). Neu
    nguoi dung hoi ve cac chi so KPI moi nay (SKU, khach tai don, SP trong tam, ASO, KH Active...):
    PHAI noi ro 2 y - (1) bo KPI nay CHUA duoc DNH ap dung chinh thuc (con dang thu nghiem, xac nhan
    voi DA phia DNH), (2) he thong cung chua co nguon du lieu de tinh. TUYET DOI KHONG tu bia/uoc
    luong so lieu, va KHONG nham lan voi KPI nhan vien HIEN TAI (nguong 80%/50%, van dang dung binh
    thuong) - 2 he thong KPI khac nhau, KHONG duoc tron lan (xem docs_kpi_luong_kinh_doanh_MN.md).
"""
