# -*- coding: utf-8 -*-
"""
Mo ta schema du lieu DNH cho AI hieu de sinh SQL dung.

NGUON DU LIEU (tu 2026-07-08):
- "local" (SQLite, file warehouse.db) la kho CHINH cho HAU HET cau hoi - duoc dong bo dinh ky
  (moi 15-30 phut) tu Bravo qua sync_warehouse.py, co INDEX + DAY DU LICH SU NHIEU NAM, tra loi
  nhanh (<=10s). Dung tool query_database cho cau hoi tu do ve doanh thu/san pham/khach hang/
  nhan vien/vung mien/tra hang khong thuoc 5 tool bao cao chuan.
- Supabase CHI con dung cho inventory (bang do dong nghiep tu nhap) - dung tool
  query_inventory_receivables. CONG NO da chuyen HAN sang kho local (bang fact_congno_khachhang,
  snapshot tu SP goc DNH) tu 29/07/2026 - KHONG con doc receivable_detail/receivable_etc tren Supabase.
- Bravo (SQL Server song, may chu that cua khach hang) la nguon fallback CHI-DOC cho object/cot chua
  duoc warehouse phu. Chatbot tim schema dong tu catalog toan bo object duoc cap quyen, sau do moi
  query live bang T-SQL. Bao cao chuan van uu tien warehouse/tool da kiem chung de nhanh va on dinh.
!!! Du lieu "local" co the tre toi da ~15-30 phut so voi Bravo that - neu nguoi dung hoi so lieu
"vua moi/ngay bay gio", noi ro day la so lieu tai lan dong bo gan nhat, khong phai tuc thoi 100%.
"""

# ==============================================================================================
# DOC TRUOC KHI THEM BANG MOI VAO SCHEMA_CONTEXT BEN DUOI
# ==============================================================================================
# Bang fact_thongketinhluong CO trong kho (xem local_warehouse.py) nhung CO Y KHONG duoc mo ta o
# day. Ly do: no co BA TANG chong len nhau (TP -> QLV -> tang la), moi tang deu bang dung doanh thu
# that, nen cong ca bang ra SAI GAP HON 3 LAN (do ky 31/07/2026: 105.122.031.617 so voi 33.307.889.644
# that). Hien AI chi cham vao no qua tool salary_detail() - ham do tra dung 1 dong cho 1 nguoi nen
# an toan. Khai bang nay vao day = mo duong cho AI tu viet SQL cong ca bang.
# NEU VAN CAN KHAI: phai viet canh bao 3 tang NGAY TRONG CUNG lan sua, khong khai truoc canh bao sau.
# Bay 2 tang cua fact_tonghopkhachhang (nhe hon) da gay 4 cau tra loi sai ngay 31/07/2026, trong do
# 2 cau bao nguoc lai voi khach rang du lieu cua ho hong - xem canh bao trong phan bang do ben duoi.
# ==============================================================================================

SCHEMA_CONTEXT = """
=== KHO "local" (SQLite) - dung voi tool query_database. Ten bang/cot deu chu thuong, KHONG can
dat trong dau ngoac kep (SQLite khong phan biet hoa/thuong nhu Postgres). Dung LIMIT N (khong dung
TOP N cua T-SQL). Ham ngay thang: date(), julianday() - cot doc_date/save_date la dang text 'YYYY-MM-DD'. ===

vhoadon_otc (moi dong la 1 dong hoa don chi tiet, kenh OTC - nha thuoc/nha phan phoi. Dong bo tu
  vHoaDonTotal ben Bravo - DA xac nhan day la nguon DAY DU, co ca cac dong dieu chinh/hoan don
  (Amount9 am) ma nguon cu (vHoaDon) am tham loai bo gay overstate doanh thu). !!! KHI QUERY TRUC TIEP SANG BRAVO: CHI dung view vHoaDonTotal (OTC) / vHoaDonETCTotal (ETC) - TUYET DOI KHONG dung vHoaDonPBI.
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

QUY TAC TRA LOI VUNG/MIEN: CHI dua so cua vung duoc hoi, KHONG tu y liet ke them vung khac hay ve bang doi chieu toan ky. CHI nhac den nhom "Khac" neu >0.5% tong. Tra loi gon.

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
  !!! CANH BAO TARGET OTC: "OTC" BAO GOM channel_code='GT' VA 'MT'. BAT BUOC SUM(amount) cho ca hai khi noi "OTC". CHI loc rieng 'GT' neu co chu "thuong"/"truyen thong". % dat target kenh MT = SUM(amount9 vhoadon_otc WHERE channel_code='ASM01') / amount dim_targetvungmien WHERE channel_code='MT'.
fact_kehoachtongetc: target tong ETC theo thang. Cot: doc_date (ngay dau thang), amount, item_group.
!!! % HOAN THANH CHI TIEU NHIEU KENH: (1) Kiem MAX(doc_date) tung kenh, (2) So sanh tren khoang thang CHUNG, (3) KHONG goi tong vai thang la chi tieu nam hay gop % 2 kenh co mau so khac ky.
dmssx_khachhang: code (ma khach hang ETC), name, city_id (dung join vung mien cho ETC), id_code (Id
  noi bo DMS, khac code), kenh_bh (kenh ban hang dang text). KHONG co cot NV DUOC GAN phu trach (khac
  dms_khachhang.emp_code ben OTC). **CHI RIENG bang danh muc khach nay thieu cot do** - TUYET DOI
  KHONG suy rong thanh 'ETC khong gan nhan vien': hoa don ETC (vhoadon_etc.employee_code, dong bo
  tu vHoaDonETCTotal.EmpDMSCode) CO du 100% va co 34 NV ban ETC (do 04/09/2026), nen MOI phan tich
  doanh thu/tang truong ETC theo nhan vien deu LAM DUOC. Da 2 lan tra loi sai vi suy rong cau nay
  (04/09/2026): noi 'ETC khong co truong NV phu trach tren hoa don' va 'ETC khong co co che giao
  chi tieu ca nhan' - ca hai deu SAI. Neu thieu du lieu thi noi ro thieu O BANG NAO, khong ket
  luan ca kenh.
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
  manager_area_code (!!! KHONG PHAI ma nguoi quan ly truc tiep cua tung nhan vien - day la ma VUNG
  DIA LY (vd V07/V08/V20/V21) ma 1 QLV dang phu trach, chi dung de gan TDV vao khu vuc ban hang.
  TUYET DOI KHONG dung cot nay de tra loi "TDV nao chua co quan ly truc tiep"/"ai la quan ly cua X" -
  se ra ket qua SAI (da xay ra that 18/08/2026: dung manager_area_code IS NULL de dem "TDV thieu quan
  ly" ra 15 nguoi theo vung, trong khi dung fact_tonghopkhachhang.manager_code thi so gan bang 0).
  Muon biet CHINH XAC ai la quan ly truc tiep cua 1 nhan vien, PHAI dung
  fact_tonghopkhachhang.manager_code (xem chi tiet o bang do ben duoi) - day la quan he THAT tu Bravo,
  duoc them 23/07/2026 chinh de THAY THE cach suy luan qua ma vung nay vi kem chinh xac hon.
  !!! NGOAI LE BAT BUOC (11/08/2026): 2 ma MBKV12 (Nguyen Thi Thanh Thuy, QLV vung MB, chi tieu
  ~5,28 ty) va TM25030101 (Lac Ngoc Sam) la NGUOI THAT dang lam viec binh thuong, bi Bravo gan NHAM
  co is_duplicate=1 (da xac minh: khong co ngay nghi viec, van phat sinh doanh so deu moi thang). Moi
  cau SQL loc COALESCE(is_duplicate,0)<>1 de TINH TOAN/XEP HANG deu PHAI them dieu kien giu lai 2 ma
  nay, vi du: "AND (COALESCE(is_duplicate,0)<>1 OR employee_code IN ('MBKV12','TM25030101'))". Neu
  quen dieu kien nay, ket qua se THIEU AM THAM 2 nguoi that ma khong co dong nao bao la da bo sot -
  da xay ra that (11/08/2026: cau hoi ve 9 QLV MB thay vi 10, thieu dung MBKV12) khi tu viet SQL thay
  vi dung tool bao cao chuan (get_revenue_tree/get_kpi_ranking/get_employee_kpi da tu dong xu ly dung
  ngoai le nay san, UU TIEN dung cac tool do cho cau hoi KPI/xep hang nhan vien thay vi tu viet SQL).
dim_chucvu: position_code, description (ten tieng Viet day du, vd TDV -> "Trinh duoc vien", QLV ->
  "Quan ly vung" - JOIN qua position_code de hien thi ten vai tro dep, DISTINCT san khi dong bo).
fact_tonghopkhachhang: 1 dong = 1 (nhan vien, khach hang, ngay snapshot). Cot: employee_code,
  customer_code, amount_ct (doanh so NV voi KH do - SUM de ra doanh so NV), month_sale_target (target
  thang, MAX vi lap lai moi dong), manager_code (!!! NGUON CHUAN DUY NHAT de biet 1 nhan vien dang bao
  cao truc tiep len ai - MAX vi lap lai moi dong; dung ISNULL/TRIM(manager_code)='' de tim nguoi THIEU
  quan ly truc tiep. TUYET DOI KHONG dung dim_nhanvien.manager_area_code hay area_code de suy luan
  quan he nay - 2 cot do chi la vung dia ly, kem chinh xac hon, xem canh bao o dim_nhanvien phia
  tren), save_date (ngay snapshot - dung MAX(save_date) <= ngay can xem de lay snapshot gan nhat),
  is_nc (=1 neu la KH moi trong thang). CHI CO ~90 NGAY GAN NHAT trong kho local (lich su xa hon
  khong dong bo vi it gia tri cho KPI hien tai).
  Cot moi tu 31/07/2026:
    year_sale_target - !!! year_sale_target: CHUA XAC NHAN KY NAO. KHONG dung de tra loi "chi tieu NAM". Noi ro he thong chua xac nhan. Dung MAX.
    is_ro = RE-ORDER (khach DAT LAI HANG trong thang) - XAC NHAN 26/08/2026. DUNG COT NAY cho cau
      "bao nhieu khach mua lai/dat lai", KHONG duoc suy dien "khong phai khach moi thi la mua lai":
      cach suy dien cu tra 6.002 trong khi so that la 5.373.
      Do 3 thang lien tiep, du lieu that: is_nc + is_ro + (khong mang co nao) = DUNG BANG tong so
      khach, khong du khong thieu thang nao (06/2026: 752+4.757+462=5.971; 07/2026: 605+5.579+643=
      6.827; 08/2026: 521+4.846+623=5.990). Khop voi nghia re-order,
    is_ac = ACTIVE CUSTOMER (khach hoat dong) - DNH chot 27/08/2026 day la co danh cho CS (Cho si)
      va TK (kenh MT/Modern Trade). is_ac KHONG phai ASO: ban ghi da co is_ac thi khong duoc gan
      hoac cong them ASO. Trong bao cao luong, CS/TK chi dung active_cus_*/is_ac; ASO chi hien o
      cac vai tro khac khi nguon co ghi nhan. Con so is_ac trong snapshot OTC van co the hep hon
      tong khach dang mua, nen phai noi ro day la co goc Bravo, khong dung no suy ra toan bo khach
      dang hoat dong; neu muon dem khach con mua thi dung is_ro hoac dem tu hoa don,
    max_customer_ord_amount (don hang lon nhat cua khach do trong ky),
    emp_dms_code (ma nhan vien theo dinh dang HOA DON - noi thang sang vhoadon_otc.employee_code ma
      khong phai vong qua dim_nhanvien),
    amount_cus - !!! CHUA RO khac amount_ct the nao ve nghiep vu. Ky 30-31/07/2026 hai cot trung
      khit, nhung cac ky 2025 lech toi 46 dong. DOANH SO VAN PHAI DUNG amount_ct; cot nay CHI de doi
      chieu khi nguoi dung hoi ro. Neu hai cot lech nhau thi NEU RO ca hai so va noi la chua xac
      nhan voi DNH cot nao chuan, KHONG duoc tu chon mot cot roi tra loi nhu the la chac chan.
  !!! is_nc, is_ro, is_ac: is_ro/ac CHI co o TANG NHAN VIEN. Luon loc tang nhan vien va COUNT(DISTINCT customer_code).
  So tren bang nay luon la LUY KE TU DAU THANG den ngay snapshot, KHONG phai so cua rieng ngay do -
  muon doi chieu voi vhoadon_otc thi phai SUM ca khoang thang ben vhoadon_otc, khong duoc lay 1 ngay.
  !!! BANG NAY CO HAI TANG CHONG LEN NHAU: TUYET DOI KHONG SUM(amount_ct) ca bang. PHAI chon tang (TDV hoac quan ly). TOT NHAT: tinh tong doanh thu tu vhoadon_otc/etc, KHONG dung bang nay.
  Bang nay KHONG co cot vung mien, phai LEFT JOIN dim_nhanvien de lay area_code - va o day co bay thu
  hai: 13 ma is_duplicate=1 khong lay duoc area_code nen roi ra thanh nhom "khong xac dinh vung" om
  9.371.467.450. Day KHONG phai loi du lieu, TUYET DOI KHONG bao la "can bo phan ky thuat kiem tra".
  (Ben Bravo cot AreaCode phu du 186/186 ma, khong sot ai - nhung co y khong keo ve bang nay de tranh
  2 nguon vung mien lech nhau; xem sync_warehouse.py::sync_fact_tonghopkhachhang.)
  Cung KHONG duoc loc bo chung cho gon - doc tiep quy tac ngay duoi.
  !!! is_duplicate: Khi TONG TIEN (doanh so, cong ty): KHONG loc is_duplicate. Khi DEM NGUOI hoac XEP HANG CA NHAN: CO loc is_duplicate.
  Rieng tool kpi_ranking(group_by='region') da xu ly dung viec nay san (gop theo manager_code, khong
  dua vao position_code lan is_duplicate) - uu tien dung tool do thay vi tu viet SQL cho cau hoi KPI
  theo vung.
  NGUONG: DAT CHI TIEU = >=100%. DAT KPI = >=80%. MUC THUONG = >=65% TDV, >=70% QLV. KHONG gop cac moc nay vao nhau.

brv_sanpham: code, name, group_code, unit (don vi tinh), id_code (khoa noi bo - dung de
  JOIN voi brv_tonkhodk.item_id, KHAC code la ma san pham dang text).
  !!! group_code RONG 100% (402/402 dong) - DA KIEM CHUNG 20/08/2026 rang CHINH NGUON Bravo
  (dbo.BRV_SanPham.GroupCode) cung rong 402/402, KHONG phai loi dong bo cua minh. TUYET DOI KHONG
  dung cot nay de tra loi "nhom san pham nao...", va KHONG bao nguoi dung la "loi dong bo".
  NHOM SAN PHAM THAT nam tren CHINH BANG HOA DON ben Bravo (query_sql_server), KHAC NHAU theo kenh
  va KHONG duoc gop chung 2 kenh vao 1 bang:
    - OTC: dbo.vHoaDonTotal.GroupCode -> bo ma DANH MUC THUONG 'DM1'/'DM2'/'DM3' (thang 7/2026:
      DM2 chiem ~94% doanh thu OTC). Day la nhom theo chinh sach thuong, KHONG phai nhom duoc ly.
    - ETC: dbo.vHoaDonETCTotal.GroupCode -> bo MA SO rieng ('0','1','3','4'...), hien CHUA co bang
      ten mo ta -> phai noi ro voi nguoi dung la chua dien giai duoc ten nhom, khong tu dat ten.
  Hai bo ma nay KHAC HE QUY CHIEU nhau nen chi duoc trinh bay TACH RIENG tung kenh.

brvsx_tralai: tra hang (CHI co kenh ETC, OTC chua co nguon). Cot: doc_date, amount9 (gia tri tra),
  is_active (=1 la hop le), stt (ma chung tu), customer_code.

brv_kho: danh muc KHO trong Bravo (co hang chuc kho vat ly/dai ly khac nhau). Cot: id_code (khoa noi
  bo, dung join voi brv_tonkhodk.warehouse_id), branch_code (**day la truong quyet dinh VUNG MIEN cho
  ton kho**: B01=San xuat/tru so chinh, B02=Kinh doanh Mien Bac, B03=Kinh doanh Mien Trung, B04=Kinh
  doanh Mien Nam - xac nhan voi DA ben Bravo 15/07/2026), code, name (ten kho cu the, vd 'Kho WHI91').
brv_tonkhodk: TON KHO DAU KY THEO TUNG NAM TAI CHINH (cot fiscal_year) - **KHONG phai ton kho hien
  tai**, va **KHONG PHAI toan bo ton kho cong ty**. Bravo giu ban ghi dau ky cua NHIEU nam
  (2024/2025/2026); PHAI loc fiscal_year = nam moi nhat, neu khong se cong don ca 3 nam va dem
  trung cung mot lo hang toi 3 lan. Ban ghi nam moi nhat duoc chot dau nam (vd 21/01/2026) va
  KHONG cap nhat trong nam - khi tra loi PHAI noi ro day la anh chup dau nam, khong duoc goi la
  'ton kho hien tai'. He kho SAN XUAT (BRVSX_TonKhoDK, ~229 ty nam 2026) CHUA duoc dong bo vao
  kho local - nghia la con so o day chi phan anh ~3% gia tri ton kho toan cong ty, PHAI neu ro
  gioi han nay thay vi trinh bay nhu tong ton kho. THAY THE nguon Supabase cu
  (bang "inventory" ben Supabase co cot "warehouse" nhung 100% NULL, KHONG dung de loc vung duoc -
  DA XAC NHAN LOI, tuyet doi khong dung Supabase cho cau hoi ton kho THEO VUNG nua, chi con Bravo/kho
  local nay moi co du lieu vung dung). Cot: warehouse_id (JOIN brv_kho.id_code de biet vung/ten kho),
  item_id (JOIN brv_sanpham.id_code de biet ten/ma san pham), quantity (so luong ton), amount (gia
  tri ton tien - nhieu dong =0 du quantity>0, PHAN LON nam o cac nam tai chinh cu; **khong duoc
  ket luan 'Bravo khong ghi gia tri'** vi he kho san xuat BRVSX_TonKhoDK co day du UnitCost/Amount.
  Neu vung nao ra 0d thi noi ro la thieu du lieu o bang nay, khong suy rong ra ca Bravo), is_active (LUON loc =1, dong is_active=0 la ban ghi cu/khong con hieu luc).
  Muon hoi "ton kho vung X": JOIN ca 3 bang (brv_tonkhodk + brv_kho + brv_sanpham), GROUP BY
  k.branch_code, loc WHERE k.branch_code='B0x' VA t.is_active=1.

fact_congno_khachhang: CONG NO theo khach hang, snapshot TUC THOI tu bao cao cong no GOC cua DNH (SP
  usp_DeptAccDueDate_GetData) - day la NGUON DUNG DUY NHAT cho cong no, dong bo dinh ky. MOT DONG =
  (khach hang x kenh): khach ban ca OTC lan ETC co 2 dong, nen truy van du no/qua han theo khach PHAI
  SUM(...) GROUP BY customer_code, TUYET DOI KHONG gia dinh 1 dong/khach. Cot: snapshot_date, snapshot_at
  (ISO datetime, dung de biet snapshot cu chua), customer_code, customer_name, sales_channel ('OTC'/'ETC'),
  area_code (MB/MB2/MN/MT), balance_end (tong du no), overdue_1_15, overdue_15_30, overdue_30_45,
  overdue_gt_45 (4 muc tuoi no theo ngay), total_overdue (=tong 4 muc, da tinh san). Ty le qua han =
  SUM(total_overdue)/SUM(balance_end). Loc vung: WHERE area_code='MB'/'MN'/'MT' (dung REGION_SQL_MARKERS,
  MB gom MB va MB2). Top khach no qua han: ORDER BY SUM(total_overdue) DESC.
  !!! CAU HOI NHAC TOI CA HAI KENH (vd "khach co du no o CA OTC VA ETC", "no theo tung kenh") - BAT
  BUOC tra ve so RIENG cua tung kenh, KHONG duoc chi tra tong gop. Trong CUNG cau SELECT, them:
      SUM(CASE WHEN sales_channel='OTC' THEN balance_end ELSE 0 END) AS otc_balance,
      SUM(CASE WHEN sales_channel='ETC' THEN balance_end ELSE 0 END) AS etc_balance,
      SUM(CASE WHEN sales_channel='OTC' THEN total_overdue ELSE 0 END) AS otc_overdue,
      SUM(CASE WHEN sales_channel='ETC' THEN total_overdue ELSE 0 END) AS etc_overdue
  (va van giu tong gop neu can). DA XAY RA THAT 2 LAN (18/08 va 20/08/2026): cau "co bao nhieu khach
  co du no o ca OTC va ETC, tong no ho the nao" chi tra duoc TONG GOP, nguoi hoi khong biet ai no OTC
  bao nhieu / ETC bao nhieu - dung y cau hoi. Gop truoc roi SUM 1 lan la MAT HAN kha nang tach lai.

=== SUPABASE (PostgreSQL) - CHI dung voi tool query_inventory_receivables ===
(Ten cot phan biet hoa/thuong, PHAI dat trong dau ngoac kep "...", dung LIMIT N)

inventory (snapshot ton kho MOI NHAT, khong theo ngay): "item_code", "item_name", "unit",
  "opening_qty", "inward_qty", "outward_qty", "closing_qty" (ton cuoi SL),
  "closing_value" (ton cuoi tien), "warehouse" (CHU Y: cot nay 100%
  NULL, KHONG dung duoc de loc/nhom theo vung - neu cau hoi co yeu to VUNG MIEN, chuyen sang dung
  query_database voi brv_tonkhodk/brv_kho/brv_sanpham o kho local thay vi bang nay).
  CHI duoc bao cao cac so snapshot da phat sinh. KHONG tinh/tra ve so thang ban het, ngay ban het,
  sap can kho hoac bat ky suy dien ton kho tuong lai nao.

(CONG NO: KHONG con tren Supabase - da chuyen sang bang fact_congno_khachhang o kho local, hoi qua
 query_database. TUYET DOI KHONG truy van receivable_detail/receivable_etc - 2 bang do la du lieu
 Excel nhap tay cu, sai lech lon, DA NGUNG dung tu 29/07/2026.)

=== QUY TAC QUAN TRONG ===
1. Doanh thu = SUM(amount9), KHONG dung cot nao khac.
2. Neu can "ngay gan nhat"/"hom nay" ma khong ro ngay cu the, dung MAX(doc_date) tu vhoadon_otc
   de tim ngay moi nhat CO DU LIEU trong kho local (co the tre vai chuc phut so voi Bravo that).
3. Khi tinh Top san pham/khach hang, LUON loai hang khuyen mai (loc unit_price > 0 cho so luong).
4. Khi JOIN dim_nhanvien de TINH TOAN/XEP HANG (KPI, doanh so theo nguoi...), LUON loc dieu kien
   O MENH DE WHERE (khong phai ON) theo dung dang: "(COALESCE(is_duplicate,0)<>1 OR employee_code
   IN ('MBKV12','TM25030101'))" - KHONG duoc viet gon thanh "COALESCE(is_duplicate,0)<>1" don thuan,
   vi se bo sot 2 nguoi that (xem chi tiet ngoai le o phan dim_nhanvien ben tren).
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
11. CHINH SACH THU NHAP TDV OTC - PHAN BIET RO BA THU KHAC NHAU, DUNG GOP:
    (A) BA MOC KPI (xac nhan voi DNH 27/07/2026): "DAT CHI TIEU" = >=100%. "DAT KPI" = >=80%, CHUNG
        cho MOI vai tro (moc danh gia hieu qua cong viec, tool get_employee_kpi/get_kpi_ranking cham
        theo moc nay). "TOI MUC THUONG NHOM HANG" = >=65% TDV (QD 0107/2026, hieu luc 01/07/2026 -
        XAC NHAN qua bang DIM_BacThuong ma thu tuc tinh luong that cua DNH doc: bac thuong TDV co
        StartDate=2026-07-01), >=70% QLV va cac cap quan ly (QD 0429/.25). 50% chi la nguong canh
        bao mau (do/vang), khong phai 1 trong 3 moc tren. TUYET DOI KHONG goi 65%/70% la "dat KPI"
        hay "dat chi tieu" - do CHI la cong cua thuong nhom hang DM1/DM2/DM3.
    (B) CHINH SACH THU NHAP TDV OTC MOI (Level/LCB, SKU, KH tai don/khach moi, V15/V22, thuong Quy/Nam): CHUA AP DUNG THUC TE cho tinh luong. KHO LOCAL CHUA CO DU LIEU cho cac chi so nay. Khong tu tinh toan so lieu.
    Voi cau hoi KPI/doanh so thong thuong (ai dat, xep hang, % hoan thanh) van dung tool
    get_employee_kpi/get_employee_daily_kpi/get_kpi_ranking binh thuong - chung da ap dung ca 3 moc
    o muc (A) va tra ve du ca 3 (count_full_target/count_kpi_achieved/count_above_target).
12. TRUOC KHI KET LUAN "BAT THUONG" / "SO LIEU KHONG DANG TIN CAY": BAT BUOC tu kiem: (a) CUNG KY khong? (b) CUNG TANG khong? (c) Nhóm "KHONG XAC DINH VUNG" la 13 ma is_duplicate=1 => binh thuong. Neu chua kiem het, TUYET DOI KHONG dung tu "bat thuong", hay tra loi "chua doi chieu duoc do...".
13. Cau hoi ve doanh thu/cong no/hoa don KHONG neu ro 1 kenh cu the (khong co chu "OTC" hay "ETC"
    rieng, vd "doanh thu thang 7", "doi soat doanh thu", "khach dang co du no") PHAI tinh CA HAI kenh
    OTC (vhoadon_otc) VA ETC (vhoadon_etc/fact_congno_khachhang WHERE sales_channel='ETC') - da xay ra
    that 18/08/2026: 1 cau doi soat view chi viet SQL cho OTC, bo sot hoan toan ETC. Khi cau hoi can
    TACH RIENG so lieu theo tung kenh (vd "tach theo kenh", "rieng OTC, rieng ETC", "ca OTC va ETC"),
    PHAI dung SUM(CASE WHEN sales_channel='OTC' THEN ... ELSE 0 END) kieu tuong tu de giu duoc so
    rieng tung kenh trong KET QUA CUOI - KHONG duoc gop chung roi SUM 1 lan vi se mat kha nang tach
    lai (da xay ra that cung ngay: 1 cau hoi "du no ca OTC va ETC" chi tra duoc tong gop, khong tach
    duoc ai no OTC bao nhieu, ETC bao nhieu du de bai yeu cau ro).
14. BA MAU SQL DE SAI KHI CAU HOI KHONG CO TOOL CO DINH (phai tu viet SQL qua query_database):
    a) "Cap san pham hay mua cung nhau" (cross-sell): 1 DON = cap (kenh, stt) - KHONG dung stt mot
       minh vi OTC va ETC co the trung so chung tu. Tu JOIN bang hoa don voi chinh no theo CUNG
       (kenh, stt) nhung item_code KHAC nhau VA co dieu kien thu tu (vd a.item_code < b.item_code)
       de: (i) khong sinh cap A-A (san pham tu ghep voi chinh no trong cung don), (ii) khong dem
       doi 1 cap thanh ca A-B lan B-A nhu 2 cap khac nhau.
    b) "Nhom san pham" (doanh thu/so ma hang theo group_code): JOIN qua brv_sanpham.group_code,
       GROUP BY group_code. So MA HANG trong nhom PHAI dung COUNT(DISTINCT item_code), KHONG dung
       COUNT(*) (se dem trung moi dong hoa don thay vi dem so ma san pham khac nhau).
    c) "Top N khach/san pham chiem bao nhieu % doanh thu TOAN CONG TY": tu so (doanh thu top N) va
       mau so (tong doanh thu cong ty) PHAI cung KY va cung NGUON/PHAM VI (vd ca hai cung tinh gop
       OTC+ETC, hoac ca hai cung chi OTC) - KHONG duoc lay tu so tu 1 truy van co pham vi khac mau
       so (vd tu so chi OTC nhung mau so gom ca ETC se lam ty le % bi sai/thoi phong).
15. PHAN RA TANG TRUONG (khach hien huu / khach moi / khach roi bo): ba phan PHAI cong lai DUNG
    BANG muc tang truong tong, phan du BANG 0. Neu con khoan "chua phan loai" hoac phai giai thich
    "chenh do cach phan bo" thi PHEP TINH DA SAI - dung lai, KHONG duoc dua ket luan.
    !!! LOI DA XAY RA 04/09/2026: bao LFL ky truoc 228,05 ty trong khi TONG ky truoc chi 226,84 ty
    (tap con lon hon tap cha - vo ly). Nguyen nhan: lay LFL theo dinh nghia RONG (gom ca khach ve 0)
    roi VAN tru them dong khach roi bo -> TRU KHACH ROI BO HAI LAN, ra -37,40 ty thay vi -13,73 ty
    (sai 2,7 lan) va ket luan sai hoan toan ve suc khoe tep khach hien huu.
    TU KIEM BAT BUOC truoc khi tra loi: (a) moi nhom con co <= tong khong? (b) cong ba nhom co ra
    dung tang truong tong khong? Chua kiem het thi khong duoc ket luan.
16. TY LE GIU CHAN THEO COHORT: "giu chan thang N" la DIEM-THOI-DIEM (co mua DUNG thang do), KHONG
    PHAI ty le con lai luy ke. TUYET DOI KHONG doc "giu chan thang 1 = 40%" thanh "mat 60% khach
    ngay sau lan mua dau" - khach nghi 1 thang roi mua lai VAN LA khach dang hoat dong.
    !!! LOI DA XAY RA 04/09/2026: ket luan "mat luon ~61-65% ngay sau lan mua dau" trong khi thuc te
    chi 20,9% khong bao gio quay lai (79,1% co mua lai). Dau hieu tu bac bo nam ngay trong bang:
    cohort 2026-04 di tu 32,8% (thang 1) LEN 42,9% (thang 3) - duong roi rung khong the TANG.
    Muon noi ve ty le roi bo thi phai tinh RIENG "khach khong mua lai BAT KY thang nao sau do",
    khong duoc suy tu con so diem-thoi-diem. Va khi so trung binh giua cac moc tuoi, PHAI so tren
    CUNG TAP COHORT (moc 6 thang chi co cohort cu nhat - so voi moc 1 thang tinh tren toan bo cohort
    la tron hai tap khac nhau).
17. TRUOC KHI NOI "KHO KHONG CO DU LIEU TRUOC NGAY X" hoac "khong du lich su de tra loi": BAT BUOC
    kiem lai bang MIN(doc_date) tren chinh bang dang dung. Xem them muc 10 - kho co lich su tu ~2022.
    !!! LOI DA XAY RA 04/09/2026: khang dinh "kho hoa don chi bat dau tu 03/09/2025, khong co lich su
    xa hon nhu mot so tai lieu mo ta" roi CAT BO du lieu dua tren khang dinh do. Hau qua: 2/5 "san
    pham moi" trong bang thuc chat da ban tu 11/2024 (mot ma da co 5,24 ty doanh thu truoc do), bo
    sot 4 san pham moi that, va tuyen bo phan "tuoi 12 thang" la bat kha thi trong khi du lieu co san.
    Khi dinh nghia "san pham moi"/"khach moi" PHAI lay lan ban dau tren TOAN BO lich su, khong phai
    lan dau xuat hien trong cua so dang xet (loi left-censoring).
18. THUONG TIEN DO V15/V22/V25 - DA DOI CO CHE TU 07/2026, KHONG PHAI LOI HE THONG:
    Do tren Bravo 04/09/2026 (FACT_ThongKeTinhLuong, toan cong ty):
      ky        V15   V22   V25   tong tien V25
      01-06/26    0     0   40-132 nguoi   62-240 trieu/thang
      07/2026    79    59    0             0
      08/2026   110    76    0             0
    V25 chay tu thang 1 den thang 6 roi DUNG HAN; V15/V22 BAT DAU dung tu thang 7. Day la DOI CO
    CHE THUONG, khong phai loi tinh luong.
    !!! LOI DA XAY RA 04/09/2026: tra loi cho QLV Pham Van Thuan (dat 81,08%) rang V25=0 la "loi ky
    thuat da biet trong thu tuc tinh luong cua DNH" va de nghi "bao ke toan kiem tra va BU THUONG".
    Neu ai lam theo thi da chi tien sai. Kiem chung: ky 31/08/2026 co 16 QLV dat >=70% va CA 16
    nguoi deu V25Bonus=0, ke ca nguoi dat 116,7% - tuc khong phai truong hop ca biet cua ai.
    QUY TAC: truoc khi noi mot khoan thuong "bi thieu/tinh sai", BAT BUOC kiem xem NGUOI KHAC cung
    dieu kien co nhan khong. Ca cong ty deu bang 0 thi do la CHINH SACH, khong phai loi. TUYET DOI
    khong de nghi bu thuong/truy linh khi chua co xac nhan cua DNH.
"""
