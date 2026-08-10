import re

with open('D:/DNH-x-MCNA/backend/schema_context.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Make substitutions to shrink the schema context.
# Target: remove wordy warnings, shorten explanations, but keep rules.
new_content = content.replace(
    '!!! KHI QUERY TRUC\n  TIEP SANG BRAVO (SQL Server that, khong phai qua tool query_database) DE DOI CHIEU/DEBUG: CHI\n  dung view vHoaDonTotal (OTC) / vHoaDonETCTotal (ETC) - TUYET DOI KHONG dung vHoaDonPBI (khac\n  nguon, cho ra doanh thu LECH ~7% so voi vHoaDonTotal do cach tinh khac nhau, da phat hien\n  27/07/2026 khi doi chieu doanh thu Mien Nam bi lech ~460 trieu vi dung nham view nay):',
    '!!! KHI QUERY TRUC TIEP SANG BRAVO: CHI dung view vHoaDonTotal (OTC) / vHoaDonETCTotal (ETC) - TUYET DOI KHONG dung vHoaDonPBI.'
)

new_content = new_content.replace(
    'QUY TAC TRA LOI cau hoi "doanh thu theo vung/mien X": CHI tra loi DUNG PHAM VI nguoi dung hoi - hoi\nrieng 1 vung (vd "doanh thu mien Nam") thi CHI dua so cua vung do, KHONG tu y liet ke them cac vung\nkhac, KHONG tu ve bang "doi chieu toan ky", KHONG chay them 1 truy van rieng de "kiem chung" roi in\nca 2 ket qua ra - nguoi dung chi can 1 cau tra loi gon, khong can xem qua trinh AI tu kiem tra dung/sai.\nLEFT JOIN dung tu no da bao dam khong mat du lieu (khach mo coi tu dong roi vao nhom rieng), nen\nKHONG can hoi lai band tong de "doi chieu" moi lan tra loi. CHI de cap den nhom "Khac/chua xac dinh"\nNEU no chiem ty trong dang ke (vd >0.5% tong) trong cung ky duoc hoi - va chi 1 cau ngan gon, KHONG\nlam bang rieng cho no. Neu nhom nay bang 0 hoac khong dang ke, KHONG noi gi ca (im lang la binh thuong,\ndung noi "khong co phat sinh chua xac dinh vung" - do la thong tin thua, nguoi dung khong hoi).',
    'QUY TAC TRA LOI VUNG/MIEN: CHI dua so cua vung duoc hoi, KHONG tu y liet ke them vung khac hay ve bang doi chieu toan ky. CHI nhac den nhom "Khac" neu >0.5% tong. Tra loi gon.'
)

new_content = new_content.replace(
    '!!! CANH BAO QUAN TRONG - LOI DA TUNG XAY RA (phat hien 23/07/2026, tai pham 27/07/2026 voi cau hoi\n  "bao cao OTC 3 mien theo target"): chu "OTC" trong cau hoi KHONG PHAI ten rieng cua channel_code=\'GT\'\n  - "OTC" la ten KENH LON (doi lap voi "ETC"), BAO GOM CA channel_code=\'GT\' (OTC thuong) VA\n  channel_code=\'MT\' (Modern Trade, cung thuoc kenh OTC ve mat phan loai kinh doanh). Cau hoi "target\n  OTC vung X", "doanh so OTC theo target", "bao cao OTC 3 mien" (chi noi "OTC" chung chung, KHONG noi\n  them "OTC thuong" hay "khong tinh Modern Trade") BAT BUOC phai SUM(amount) CA channel_code=\'GT\' VA\n  channel_code=\'MT\' cho tung area_code cung doc_date - CHI loc channel_code=\'GT\' se lam target vung\n  MN bi THIEU ~40% (vd thang 7/2026: GT=7.89 ty, MT=5.29 ty rieng, tong dung phai la 13.19 ty - da\n  tung bao thieu MT khien target hien ra thap hon thuc te, ke ca trong bao cao tong hop 3 mien).\n  CHI duoc loc rieng channel_code=\'GT\' (loai tru MT) khi nguoi dung noi RO RANG gioi han o kenh do -\n  vd "target kenh OTC THUONG" (co chu "thuong"), "target GT khong tinh Modern Trade", "target rieng\n  kenh truyen thong" - PHAI co tu ngu tuong minh loai tru MT, KHONG duoc suy dien tu viec cau hoi\n  chi go chu "OTC" don thuan. Neu khong chac chan y nguoi dung la gi, LUON cong ca GT+MT va neu ro\n  trong cau tra loi rang so lieu da gom ca Modern Trade thay vi tu y loai tru. Cau hoi "kenh MT dat\n  bao nhieu % chi tieu" (chi rieng kenh MT) -> SUM(amount9) tu vhoadon_otc WHERE channel_code=\'ASM01\'\n  (xem canh bao MT o dim_tinhthanhpho phia tren) chia cho amount tu dim_targetvungmien WHERE\n  channel_code=\'MT\' AND doc_date=ngay dau thang dang hoi.',
    '!!! CANH BAO TARGET OTC: "OTC" BAO GOM channel_code=\'GT\' VA \'MT\'. BAT BUOC SUM(amount) cho ca hai khi noi "OTC". CHI loc rieng \'GT\' neu co chu "thuong"/"truyen thong". % dat target kenh MT = SUM(amount9 vhoadon_otc WHERE channel_code=\'ASM01\') / amount dim_targetvungmien WHERE channel_code=\'MT\'.'
)

new_content = new_content.replace(
    '!!! HAI KENH KHONG CO CHI TIEU CHO CUNG SO THANG - BAY NAY GAY KET LUAN NGUOC (do 31/07/2026):\n  OTC (dim_targetvungmien)  chi co chi tieu den het THANG 7/2026 -> cong lai 389.303.222.378.\n  ETC (fact_kehoachtongetc) co du CA 12 THANG                    -> cong lai 503.163.621.222.\n  Cong bua ca hai roi goi la "chi tieu nam" se ra OTC 78,8% (mau so 7 thang) vs ETC 44,9% (mau so 12\n  thang), dan den ket luan "OTC tot, ETC cham". KET LUAN DO SAI: chenh lech den tu DO DAI KY khac\n  nhau chu khong phai tu hieu suat. Da xay ra that voi nguoi dung ngay 31/07/2026.\n  => Khi tinh "% hoan thanh chi tieu" cho NHIEU KENH, BAT BUOC:\n     (1) Kiem MIN/MAX(doc_date) chi tieu cua TUNG kenh TRUOC khi cong.\n     (2) Neu hai kenh khac so thang, CHI so tren khoang thang CHUNG va NOI RO dang tinh cho ky nao.\n     (3) TUYET DOI KHONG goi tong cua vai thang la "chi tieu nam", va KHONG gop % cua hai kenh co\n         mau so khac ky thanh mot con so "tong".',
    '!!! % HOAN THANH CHI TIEU NHIEU KENH: (1) Kiem MAX(doc_date) tung kenh, (2) So sanh tren khoang thang CHUNG, (3) KHONG goi tong vai thang la chi tieu nam hay gop % 2 kenh co mau so khac ky.'
)

new_content = new_content.replace(
    '!!! CHUA XAC NHAN LA CHI TIEU CUA KY NAO. Do tren Bravo ky 31/07/2026, cong o\n      tang quan ly (= cap cong ty) ra 327.132.314.370, tuc chi bang 6,42 lan chi tieu thang 7\n      (50.967.586.921) - KHONG phai 12 thang, cung KHONG bang 389.303.222.378 la tong chi tieu OTC 7\n      thang da cong bo. Hai tang con cho hai so khac nhau (quan ly 327 ty, nhan vien 360 ty), khac\n      han month_sale_target von khop tuyet doi voi chi tieu cong ty. => TUYET DOI KHONG dung cot nay\n      de tra loi "dat bao nhieu % chi tieu NAM" cho toi khi DNH xac nhan no la chi tieu cua ky nao.\n      Neu nguoi dung hoi, noi ro la he thong co so nhung chua xac nhan y nghia ky han. Dung MAX chu\n      khong SUM (lap lai moi dong giong month_sale_target - da kiem: 185/186 NV co dung 1 gia tri),',
    '!!! year_sale_target: CHUA XAC NHAN KY NAO. KHONG dung de tra loi "chi tieu NAM". Noi ro he thong chua xac nhan. Dung MAX.'
)

new_content = new_content.replace(
    '!!! BA CO KHACH HANG HANH XU KHAC NHAU GIUA 2 TANG - do that tren Bravo ky 31/07/2026:\n        tang QUAN LY  : is_nc=577 | is_ro=0     | is_ac=0\n        tang NHAN VIEN: is_nc=601 | is_ro=5.594 | is_ac=45\n    - is_nc CO tren CA HAI tang -> dem ca bang se CONG CHONG, phai loc 1 tang.\n    - is_ro va is_ac CHI co tren tang NHAN VIEN, tang quan ly toan bo bang 0 -> neu loc nham sang\n      tang quan ly se tra ve "0 khach mua lai", sai hoan toan nhung trong rat giong so that.\n    => Cau hoi ve khach mua lai / khach hoat dong: BAT BUOC loc TANG NHAN VIEN (employee_code KHONG\n       xuat hien lam manager_code cua ai). Va luon COUNT(DISTINCT customer_code), khong dem theo dong.',
    '!!! is_nc, is_ro, is_ac: is_ro/ac CHI co o TANG NHAN VIEN. Luon loc tang nhan vien va COUNT(DISTINCT customer_code).'
)

new_content = new_content.replace(
    '!!! BANG NAY CO HAI TANG CHONG LEN NHAU - CAI BAY NGHIEM TRONG NHAT CUA CA KHO !!!\n  Moi khoan doanh so duoc ghi HAI LAN: mot dong gan TDV, mot dong gan QUAN LY cua TDV do (qua\n  manager_code). Da kiem chung tren Bravo ky 31/07/2026: tang quan ly = 33.307.889.644, tang nhan\n  vien = 33.307.889.644, va doanh thu OTC thang 7 that tinh tu vhoadon_otc CUNG = 33.307.889.644 -\n  trung khit den tung dong. Cong ca bang ra 66.615.779.288, tuc DUNG GAP 2 LAN doanh thu that.\n  => TUYET DOI KHONG viet SUM(amount_ct) tren toan bang de ra "tong doanh so cong ty". PHAI CHON MOT\n     TANG truoc khi cong:\n     - Cau hoi ve nhan vien ban hang: JOIN dim_nhanvien, loc position_code=\'TDV\' (tang duoi).\n     - Cau hoi cap cong ty/vung: chi lay cac ma co xuat hien lam manager_code cua nguoi khac (tang tren).\n     - TOT NHAT: dung cau hoi ve TONG DOANH THU thi KHONG dung bang nay - dung vhoadon_otc/vhoadon_etc\n       voi SUM(amount9), do moi la nguon doanh thu chuan va khong bi cong chong.',
    '!!! BANG NAY CO HAI TANG CHONG LEN NHAU: TUYET DOI KHONG SUM(amount_ct) ca bang. PHAI chon tang (TDV hoac quan ly). TOT NHAT: tinh tong doanh thu tu vhoadon_otc/etc, KHONG dung bang nay.'
)

new_content = new_content.replace(
    '!!! is_duplicate: LOC HAY KHONG LA TUY MUC DICH - LOC NHAM CHO LA MAT TIEN THAT !!!\n  4 trong so cac ma is_duplicate=1 la QLV THAT bi Bravo gan nham co trung lap (MN1 "Kenh MT" tuc kenh\n  Modern Trade, MN4 "Cho si", MBKV12, TM25030101) - ho om doanh thu THAT. Kiem chung ky 31/07/2026,\n  tinh tren tang quan ly:\n     KHONG loc is_duplicate -> 33.307.889.644 = DUNG BANG doanh thu OTC that tu vhoadon_otc\n     CO loc is_duplicate    -> 24.381.156.216 = MAT 8.926.733.428 (26,8%) tien THAT\n  => Khi tinh TONG TIEN (tong doanh so, doanh thu vung, doanh thu cong ty): chon MOT TANG va KHONG\n     loc is_duplicate. Muon biet vung mien thi phai chap nhan nhom "chua ro vung" va NOI RO ra, chu\n     khong duoc loc bo de bang cho dep.\n  => Khi DEM SO NGUOI hoac XEP HANG CA NHAN (ai dat KPI, top nhan vien, bao nhieu nguoi dat chi tieu):\n     CO loc is_duplicate, vi ma bong khong phai nguoi that de dem/xep hang.',
    '!!! is_duplicate: Khi TONG TIEN (doanh so, cong ty): KHONG loc is_duplicate. Khi DEM NGUOI hoac XEP HANG CA NHAN: CO loc is_duplicate.'
)

new_content = new_content.replace(
    'NGUONG tren amount_ct/month_sale_target - PHAN BIET BA MOC, TUYET DOI KHONG GOP:\n  "DAT CHI TIEU" = >=100%. "DAT KPI" = >=80% (CHUNG cho moi vai tro - moc danh gia hieu qua cong\n  viec). "DAT MUC THUONG NHOM HANG" = >=65% voi TDV (QD 0107/2026), >=70% voi QLV va cac cap quan ly\n  (QD 0429/.25) - moc nay KHAC NHAU THEO VAI TRO nen khi tu viet SQL phai JOIN dim_nhanvien.position_code\n  moi lay dung. Dung goi moc 65%/70% la "dat chi tieu" hay "dat KPI"; cung dung goi la "nguong huong\n  thuong" chung chung (do chi la cong cua thuong nhom hang DM1/DM2/DM3, con V15/V22/ASO/thuong\n  quy-nam co moc rieng).',
    'NGUONG: DAT CHI TIEU = >=100%. DAT KPI = >=80%. MUC THUONG = >=65% TDV, >=70% QLV. KHONG gop cac moc nay vao nhau.'
)


with open('D:/DNH-x-MCNA/backend/schema_context.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
