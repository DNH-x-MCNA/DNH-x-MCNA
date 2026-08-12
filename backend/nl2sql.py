# -*- coding: utf-8 -*-
"""NL2SQL: dung Claude (tool use) de hieu cau hoi tieng Viet, tra loi tu nhien.

Kien truc HYBRID de tang do chinh xac cho cac bao cao hay dung:
  - Cau hoi thuoc nhom bao cao CHUAN (doanh thu theo kenh, top san pham, top khach hang,
    vung mien, KPI nhan vien, so sanh 2 khoang thoi gian) -> goi truc tiep cac ham da kiem chung
    trong report_templates.py, AI KHONG tu sinh SQL cho nhom nay.
  - Cau hoi AD-HOC ngoai cac mau tren -> fallback ve tool query_database (local SQLite) hoac
    query_inventory_receivables (Supabase, chi cho ton kho/cong no).

CA 2 nhom deu doc tu kho "local" (SQLite dong bo dinh ky tu Bravo) - KHONG con goi Bravo song
truc tiep tu chatbot nua, giup tra loi nhanh (<=10s) va khong phu thuoc VPN on dinh moi luc.

Ho tro NHO NGU CANH da luot (conversation_memory.py) - moi session (1 phien chat webapp) duoc
nho lai vai cau hoi/tra loi gan nhat, de cau hoi tiep theo khong can nhac lai tu dau.
"""
import os
import json
from collections import defaultdict
import anthropic
from schema_context import SCHEMA_CONTEXT
from query_engine import run_query
from report_templates import call_template, latest_data_date, sync_freshness_note
from conversation_memory import load_history, append_message, get_query_state, set_query_state
from realtime_context import REALTIME_TOOLS, REALTIME_TOOL_NAMES, get_current_datetime, resolve_relative_date
from glossary_memory import save_glossary_term, retrieve_relevant_glossary
from longterm_memory import save_example, retrieve_similar_examples
from cost_logger import compute_and_log_cost

MODEL = "claude-sonnet-5"
MAX_TOOL_ROUNDS = 4  # 04/08/2026: giam tu 8 -> 4 (tiet kiem thoi gian + token). Tool Merger da gop
                      # nhieu tool call thanh 1, nen 4 vong la du cho moi tinh huong thuc te.
                      # 10/08/2026: GIU NGUYEN 4. Ca 2 ca "cau hoi qua phuc tap" truy duoc nguyen nhan
                      # trong ngay (get_audit_log, get_revenue_tree) deu do MO TA TOOL chua ro khien
                      # model goi lap, sua cau chu la het - khong phai do thieu vong.
MAX_TOOLS_PER_ROUND = 5  # 10/08/2026: truoc day so 3 nam hardcode giua ham ask(). Nang 3 -> 5 vi sau
                          # khi va loi Tool Merger (xem _merge_bulk_tool_calls), cac lenh goi KHAC
                          # tham so nay chay THAT thay vi bi bo am tham, nen can them cho.
MAX_ROWS_TO_MODEL = 20 # Giam tu 50 -> 30 -> 20 tiet kiem token (ad-hoc SQL, template tools khong dung)
MAX_HISTORY_TURNS = 4  # 04/08/2026: giam tu 6 -> 4 tiet kiem token (ngu canh 4 luot la du, moi luot
                       # cu cong don token lich su khien vong sau cham di dang ke)
MAX_TOKENS = 6144  # 04/08/2026: giam tu 8192 -> 6144 ep Claude tra loi ngan gon hon, giam thoi gian
                   # sinh output (~2-3s nhanh hon). Van du cho thinking + bang 30 dong.
MAX_PAYLOAD_CHARS = 6000  # Gioi han ky tu payload gui cho AI (~1500 tokens). Template tools (employee_kpi,
                          # revenue_tree...) tra JSON KHONG gioi han kich thuoc, truoc day co the len 20K-50K
                          # chars, gay phình context 7K->49K tokens khi AI goi nhieu tool lien tiep. last_result
                          # (cho UI) VAN giu nguyen day du, chi phan gui cho AI bi cat.

TEMPLATE_TOOLS = [
    {
        "name": "get_revenue_by_channel",
        "description": "Doanh thu + so hoa don theo kenh OTC va ETC trong 1 khoang ngay. "
                        "Truy van DA KIEM CHUNG khop 100% voi Bravo - UU TIEN dung tool nay cho moi cau hoi ve doanh thu theo kenh/tong doanh thu.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Ngay bat dau, dinh dang YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "Ngay ket thuc, dinh dang YYYY-MM-DD"},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_top_products",
        "description": "Top N san pham theo doanh thu trong 1 khoang ngay (da tu dong loai hang khuyen mai khoi so luong). "
                        "UU TIEN dung tool nay cho moi cau hoi ve san pham ban chay/top san pham. Tu dong tra ve top san pham cua rieng doi QLV neu duoc hoi.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "So luong top can lay, mac dinh 10"},
                "channel": {"type": "string", "enum": ["OTC", "ETC", "ALL"], "description": "Kenh, mac dinh ALL (ca 2 kenh)"},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_top_customers",
        "description": "Top N khach hang theo doanh thu trong 1 khoang ngay. "
                        "UU TIEN dung tool nay cho moi cau hoi ve khach hang mua nhieu nhat/top khach hang.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "So luong top can lay, mac dinh 10"},
                "channel": {"type": "string", "enum": ["OTC", "ETC", "ALL"], "description": "Kenh, mac dinh ALL"},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_revenue_by_region",
        "description": "Doanh thu theo vung mien (Mien Bac/Trung/Nam) trong 1 khoang ngay. "
                        "BAT BUOC dung tool nay cho MOI cau hoi ve doanh thu theo vung/mien/khu vuc - KE CA "
                        "KHI nguoi dung chi hoi 1 vung cu the (vd 'doanh thu mien Nam'): van goi tool nay "
                        "(no luon tra ve ca 3 vung) roi CHI trich/hien thi vung duoc hoi trong cau tra loi, "
                        "TUYET DOI KHONG tu viet SQL rieng voi dieu kien area_code=... vi se BO SOT khach "
                        "hang 'mo coi' (khong co ho so trong bang khach hang) ma CHI ham nay moi suy luan "
                        "dung vung qua tien to ma khach hang. "
                        "THAM SO 'channel' QUAN TRONG (28/07/2026, sua sau khi phat hien bao cao 'OTC 3 mien' "
                        "bi thoi phong ~4 lan neu quen loc): nguoi dung hoi RO RANG 'doanh thu OTC theo vung' "
                        "-> BAT BUOC truyen channel='OTC'; hoi 'ETC theo vung' -> channel='ETC'; hoi 'doanh "
                        "thu theo vung' CHUNG CHUNG (khong noi OTC/ETC) -> de channel mac dinh 'ALL' (gop ca "
                        "2 kenh). KHONG duoc de mac dinh 'ALL' roi tu tru/suy doan phan OTC - 1-2 khach ETC "
                        "(benh vien/thau) co the lon hon CA VUNG do cong lai, lam so bi sai nghiem trong. "
                        "CANH BAO NHAM LAN QUAN TRONG: 'Kenh MT' (Modern Trade - chuoi nha thuoc lon nhu "
                        "Long Chau, Pharmacity) LA 1 KENH BAN HANG (CHI thuoc OTC), HOAN TOAN KHAC voi ma vung "
                        "'MT'=Mien Trung (trung chu viet tat ngau nhien). Neu nguoi dung hoi 've doanh thu "
                        "Kenh MT/Modern Trade/MN1' thi VAN goi tool NAY (KHONG phai get_revenue_by_channel, "
                        "tool do chi biet OTC/ETC toan quoc khong tach vung) - dong ket qua cua Mien Nam se "
                        "co them truong 'channel_breakdown' (danh sach {name, revenue}) chua san doanh thu "
                        "Kenh MT da tach rieng (SO NAY DA NAM SAN trong 'revenue' cua Mien Nam, KHONG duoc "
                        "cong them) - lay so tu day de tra loi. TUYET DOI KHONG tra loi 'he thong khong co "
                        "kenh MT' hay tu dong hieu nham sang doanh thu vung Mien Trung khi nguoi dung noi ro "
                        "la 'kenh'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "channel": {"type": "string", "description": "'ALL' (mac dinh, gop OTC+ETC), 'OTC', hoac 'ETC' - "
                                                               "PHAI truyen dung khi nguoi dung noi ro kenh, xem canh bao o description."},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_employee_kpi",
        "description": "KPI nhan vien tu snapshot gan nhat <= as_of_date. Tra ve total_employees + 3 muc do "
                        "rieng: count_full_target (dat chi tieu), count_kpi_achieved (dat KPI), "
                        "count_above_target/count_below_target (toi muc thuong nhom hang) - dinh nghia/nguong "
                        "day du cua 3 muc nay va y nghia mau status da co o system prompt, KHONG tu suy dien "
                        "lai o day. "
                        "UU TIEN dung cho MOI cau hoi ve KPI/doanh so nhan vien TONG QUAN/xep hang (ke ca ma "
                        "khu vuc MBKV*/ASM*) - KHONG dung cho KPI THEO NGAY 1 nguoi (dung get_employee_daily_kpi). "
                        "Voi cau hoi 'ai chua dat KPI/target' -> dung filter='below_target' (KHONG dung limit lon "
                        "roi tu loc thu cong, gay ton du lieu va co the khong tra loi duoc). "
                        "Voi cau hoi chi dinh ro VAI TRO (vd 'top TDV', 'cac QLV chua dat KPI') -> BAT BUOC dung "
                        "tham so position_code (vd 'TDV','QLV') de loc NGAY TU DAU, TUYET DOI KHONG tu loc thu "
                        "cong ket qua sau khi nhan ve (da tung gay sot du lieu, vd 1 QLV lot vao top TDV).",
        "input_schema": {
            "type": "object",
            "properties": {
                "as_of_date": {"type": "string", "description": "Tinh KPI luy ke den ngay nay, dinh dang YYYY-MM-DD"},
                "limit": {"type": "integer", "description": "So luong nhan vien can lay trong danh sach ket qua, mac dinh 10"},
                "order_by": {"type": "string", "enum": ["sales", "pct"], "description": "Chi ap dung khi filter='all': xep hang theo doanh so tuyet doi hay % dat target, mac dinh sales"},
                "filter": {"type": "string", "enum": ["all", "below_target", "above_target"],
                           "description": "'all'=top N tot nhat (mac dinh), 'below_target'=CHUA toi muc huong thuong (te nhat truoc), 'above_target'=DA toi muc huong thuong (tot nhat truoc). Muc huong thuong lay THEO VAI TRO cua tung nguoi (TDV 65%, quan ly 70%). LUU Y day KHONG phai moc 'dat chi tieu' (=100%) - muon dem so nguoi dat chi tieu thi doc 'count_full_target' trong ket qua"},
                "position_code": {"type": "string", "description": "Loc theo vai tro cu the: TDV/QLV/CTV/CS/TP/PP/TBP/TK (khong bat buoc - de trong neu hoi chung tat ca vai tro). TP = Truong phong = Giam doc Mien = Giam doc Kenh (cap quan ly mien/kenh). TK = Truong kenh = Truong kenh MT (Modern Trade) - cap QLV, KHONG phai TP. CS = Cho si - cung cap QLV."},
            },
            "required": ["as_of_date"],
        },
    },
    {
        "name": "get_employee_daily_kpi",
        "description": "KPI THEO NGAY cho 1 nhan vien BAN HANG CA NHAN - tuc TRINH DUOC VIEN (TDV), "
                        "ma co xuat hien truc tiep tren hoa don, vd 'TM25010199'. TUYET DOI KHONG dung "
                        "cho cap QUAN LY (QLV/TP/PP/TBP, vd 'tungtx', 'MBKV1', 'ASM*'): ma quan ly khong "
                        "nam tren hoa don nen ket qua se ra 0 dong MOI NGAY - do la THIEU DU LIEU, khong "
                        "phai ho ban duoc 0 dong. Voi cap quan ly PHAI dung get_employee_kpi (KPI thang) "
                        "hoac get_revenue_tree (doanh so ca doi). "
                        "Trong 1 thang. Target 1 ngay = 4% MonthSaleTarget cua nhan vien do "
                        "(4% = 100% cua ngay). Ket qua co san 'days' (danh sach tung ngay T2-T6 trong thang, "
                        "moi ngay co 'status': 🔴 Do <2.5%, 🟡 Vang 2.5%-3.5%, 🟢 Xanh >3.5% - LUON dung "
                        "nguyen status nay, khong tu tinh nguong khac) va dem san count_red/count_yellow/"
                        "count_green. 'month_pct_of_target' la % TONG CA THANG (thuc te/target*100, cach "
                        "tinh CU, KHONG lien quan gi 4%/ngay va KHONG co mau) - chi dung khi hoi tong ket "
                        "cuoi thang. KHONG dung tool nay cho ma khu vuc/quan ly vung (MBKV*, ASM*, cac ma "
                        "khong xuat hien truc tiep tren hoa don) - truong hop do dung get_employee_kpi thay the.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_code": {"type": "string", "description": "Ma TDV ban hang ca nhan, vd 'TM25010199' (KHONG dung ma quan ly QLV/TP/PP hay ma khu vuc)"},
                "year_month": {"type": "string", "description": "Thang can xem, dinh dang YYYY-MM"},
            },
            "required": ["employee_code", "year_month"],
        },
    },
    {
        "name": "compare_periods",
        "description": "So sanh nhanh tong doanh thu (OTC+ETC) giua 2 khoang thoi gian bat ky (vd thang nay vs "
                        "thang truoc, quy nay vs cung ky nam truoc). Kho local co day du lich su tu ~2022 nen "
                        "so sanh xa duoc, khong chi vai ngay gan day. UU TIEN dung tool nay cho moi cau hoi so sanh.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from_a": {"type": "string", "description": "YYYY-MM-DD, dau ky can xem (ky hien tai/moi)"},
                "date_to_a": {"type": "string", "description": "YYYY-MM-DD, cuoi ky can xem"},
                "date_from_b": {"type": "string", "description": "YYYY-MM-DD, dau ky doi chieu (ky truoc/cu)"},
                "date_to_b": {"type": "string", "description": "YYYY-MM-DD, cuoi ky doi chieu"},
            },
            "required": ["date_from_a", "date_to_a", "date_from_b", "date_to_b"],
        },
    },
    {
        "name": "get_revenue_forecast",
        "description": "UOC TINH doanh thu CA THANG (OTC/ETC/tong) cho 1 thang - dung cho cau hoi "
                        "'du bao/du phong/uoc tinh doanh thu thang X'. Mo hinh: trung binh doanh thu "
                        "DUNG THANG DO cua toi da 3 nam gan nhat; da doi dau voi 20 mo hinh phuc tap "
                        "hon (he so tang truong, trung vi, hybrid...) tren 49 thang du lieu that va "
                        "thang tat ca. KHONG dung du lieu trong thang dang chay nen tra loi duoc ngay "
                        "tu dau thang. Tool TU DO sai so cua chinh no tren dung pham vi dang hoi va "
                        "tra ve 'khoang_uoc_tinh' + 'sai_so_trung_binh_pct'. "
                        "BAT BUOC khi tra loi: noi ro day la UOC TINH, neu kem khoang uoc tinh va sai "
                        "so, va (neu la thang dang chay) tach bach so luy ke THUC TE voi so uoc tinh. "
                        "Neu tra ve 'ly_do_khong_du_bao' thi noi thang la khong du bao duoc, KHONG bia so.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year_month": {"type": "string",
                                "description": "Thang can du bao, dang YYYY-MM (vd '2026-08'). "
                                               "Bo trong = thang hien tai."},
            },
            "required": [],
        },
    },
    {
        "name": "get_customer_detail",
        "description": "Chi tiet 1 khach hang cu the (theo ma khach hang): gop doanh thu thuc te trong "
                        "1 khoang ngay + so don hang + gia tri TB/don, CUNG LUC voi du no cuoi ky/no qua han "
                        "(snapshot ky gan nhat, KHONG theo khoang ngay da chon) va thong tin mapping: tinh/"
                        "thanh pho, mien (area_code MB/MT/MN), ma+ten+VAI TRO cua nhan vien phu trach "
                        "(position_label: vd 'Trinh duoc vien'/'Quan ly vung'). "
                        "UU TIEN dung tool nay cho moi cau hoi ve 1 khach hang cu the (vd 'khach hang X doanh "
                        "thu bao nhieu, ai phu trach, con no khong'). "
                        "LUU Y: kenh ETC KHONG co NV phu trach truc tiep gan tren khach hang (chi OTC co) - "
                        "voi khach ETC thuan tuy, cac truong employee_code/employee_name/position_label se rong, "
                        "KHONG phai loi.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_code": {"type": "string", "description": "Ma khach hang can xem chi tiet"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD, dau ky tinh doanh thu"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD, cuoi ky tinh doanh thu"},
            },
            "required": ["customer_code", "date_from", "date_to"],
        },
    },
    {
        "name": "get_employee_directory",
        "description": "Tra cuu MAPPING ma nhan vien <-> ten <-> vai tro (position_label, vd 'Trinh duoc "
                        "vien'/'Quan ly vung'). Dung khi nguoi dung hoi theo TEN thay vi ma (vd 'ma nhan vien "
                        "cua Nguyen Van A la gi', '[ten] la ai', 'danh sach TDV vung MB', 'liet ke cac QLV') - "
                        "KHONG can biet ma truoc. UU TIEN dung tool nay truoc khi goi cac tool KPI nhan vien "
                        "khac neu cau hoi chi cho ten (chua co ma) - tra ma xong roi moi goi tiep tool KPI "
                        "tuong ung neu can.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Tim gan dung theo ten hoac ma nhan vien (khong bat buoc)"},
                "position_code": {"type": "string", "description": "Loc theo vai tro: TDV/QLV/CTV/CS/TP/PP/TBP/TK (khong bat buoc). TP = Truong phong = Giam doc Mien = Giam doc Kenh (cap quan ly mien/kenh). TK = Truong kenh = Truong kenh MT (Modern Trade) - cap QLV, KHONG phai TP. CS = Cho si - cung cap QLV."},
                "area_code": {"type": "string", "description": "Loc theo vung: MB/MT/MN (khong bat buoc)"},
                "limit": {"type": "integer", "description": "So luong toi da tra ve, mac dinh 30"},
            },
            "required": [],
        },
    },
    {
        "name": "check_order_timing",
        "description": "Phat hien dau hieu 'chay don don KPI' (tao/sua hoa don backdate gan cuoi ky "
                        "de kip chi tieu): so sanh created_at (thoi diem BAN GHI THUC SU duoc tao trong "
                        "Bravo) voi doc_date (ngay chung tu tren hoa don, co the bi chon tay) - liet ke "
                        "cac hoa don co do lech >= threshold_days. Ket qua co san 'summary_by_employee' "
                        "(ai co nhieu don bat thuong nhat - xep dau tien) va 'top_detail' (chi tiet tung "
                        "don lech nhieu nhat). UU TIEN dung tool nay cho cau hoi kieu 'co ai chay don gia "
                        "KPI khong', 'kiem tra don hang bat thuong', 'don nay tao ngay nao'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "YYYY-MM-DD, dau ky can kiem tra (thuong la ca thang can soi)"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD, cuoi ky can kiem tra"},
                "threshold_days": {"type": "integer", "description": "So ngay lech toi thieu de bi liet ke la bat thuong, mac dinh 2"},
                "limit": {"type": "integer", "description": "So luong chi tiet toi da tra ve trong top_detail, mac dinh 20"},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_inventory_by_region",
        "description": "Ton kho (so luong + gia tri) theo vung, tu Bravo (thay the Supabase - bang cu "
                        "khong loc vung duoc). BAT BUOC dung tool nay cho MOI cau hoi ve ton kho co yeu "
                        "to vung mien (vd 'ton kho mien Nam'), KE CA khi tai khoan bi gioi han vung -"
                        "day la tool DUY NHAT con hoat dong cho ho vi tool SQL tu do da bi tat.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area_code": {"type": "string", "description": "Loc theo 1 vung: 'MB'/'MT'/'MN' (khong bat buoc - bo trong de xem ca 4 vung gom ca San xuat)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_receivables_overview",
        "description": "Tong quan CONG NO toan cong ty (hoac 1 vung neu tai khoan bi gioi han): tong du "
                        "no, tong no qua han, ty le qua han, tach theo kenh OTC/ETC va theo vung, va top N "
                        "khach no qua han nhieu nhat. Nguon: bao cao cong no GOC cua DNH (SP), dong bo dinh "
                        "ky vao kho local. BAT BUOC dung tool nay cho cau hoi cong no TONG HOP/NHIEU KHACH "
                        "(vd 'tong no qua han', 'top khach no', 'ty le qua han theo vung') - KHONG tu sinh "
                        "SQL va KHONG dung bang receivable_detail/receivable_etc cu (da ngung). Cong no cua "
                        "MOT khach cu the -> dung get_customer_detail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "top_n": {"type": "integer", "description": "So khach no qua han nhieu nhat can liet ke (mac dinh 10)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_qlv_change_history",
        "description": "Lich su ai tung/dang phu trach tung khu vuc nho (zone noi bo) - dung khi hoi "
                        "'QLV vung X tung doi qua ai', 'QLV nay lam tu bao gio'. CANH BAO: day la suy "
                        "luan gian tiep tu quy uoc dat ten (Bravo KHONG co bang lich su nhan su chinh "
                        "thuc), ~30% khu vuc se tra ve 'Chua xac dinh' - PHAI noi ro voi nguoi dung day "
                        "la han che du lieu THAT, KHONG duoc tu suy doan/bia them de lap day cho trong.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area_code": {"type": "string", "description": "Loc theo vung MB/MT/MN (tuy chon - hien tat ca khu vuc trong vung)"},
                "qlv_search": {"type": "string", "description": "Tim theo ten/ma 1 QLV cu the de xem lich su khu vuc cua rieng ho (tuy chon)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_revenue_tree",
        "description": "Cay doanh thu/KPI 3 cap: Truong phong (=GD Mien =GD Kenh) -> QLV (gom ca Truong "
                        "kenh MT va Cho si) -> Trinh duoc vien, dung "
                        "khi hoi kieu 'doanh so mien nay chia theo QLV/TDV the nao', 'cay to chuc doanh "
                        "thu vung X'. LUON dung tool nay cho cau hoi co ca 3 cap cung luc, KHONG tu ghep "
                        "nhieu tool KPI rieng le. Ket qua RAT DAI neu khong loc vung - KHUYEN KHICH truyen "
                        "area_code khi hoi ve 1 vung cu the.",
        "input_schema": {
            "type": "object",
            "properties": {
                "area_code": {"type": "string", "description": "Loc theo 1 vung MB/MT/MN (khuyen khich dung, de tranh ket qua qua dai)"},
                "as_of_date": {"type": "string", "description": "YYYY-MM-DD, mac dinh la hom nay (lay snapshot KPI gan nhat truoc/bang ngay nay)"},
            },
            "required": [],
        },
    },
    # 10/08/2026: GO tool "get_kpi_forecast_model1" khoi danh sach tool kha dung.
    # Ly do truc tiep: no CRASH 100% so lan goi, va da nhu vay tu ngay duoc viet (309d2f2, 06/08).
    # forecast_model1() truy van "SELECT t.manager_code ... FROM dim_targetvungmien t" nhung bang do
    # CHI CO 4 cot (area_code, channel_code, amount, doc_date - xem local_warehouse.py:52 va
    # sync_warehouse.py::SMALL_TABLES). Cot manager_code CHUA TUNG ton tai. Da chay thu tren may 24
    # (10/08): "OperationalError: no such column: t.manager_code".
    # Ngoai loi chet nguoi tren, con 6 van de PHAI xu ly truoc khi bat lai - xem khoi ghi chu day du o
    # report_templates.py ngay tren def forecast_model1(). Tom tat: nhan "(VUOT TARGET)" dan cung, note
    # dan cung choi lai so vua tinh, 4 cho bia so khi thieu du lieu, bo qua phan quyen vung/doi,
    # target_month la tham so trang tri, va mau so co phan la so doan (est_mb_target 19,5 ty +
    # target_etc_national 42,5 ty khong lay tu bang nao).
    # Ham forecast_model1() va TEMPLATES entry duoc GIU LAI de sua tiep sau demo 13/08; go o day la du
    # de model khong the goi (tool khong nam trong danh sach thi khong goi duoc).
    {
        "name": "get_kpi_ranking",
        "description": "Xep hang % dat KPI, TOT NHAT truoc - dung khi hoi 'QLV nao dat KPI tot/kem "
                        "nhat', 'xep hang cac vung theo KPI', 'so sanh KPI giua cac QLV/vung'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "group_by": {"type": "string", "description": "'qlv' (xep hang tung QLV, mac dinh) hoac 'region' (gop theo vung MB/MT/MN)"},
                "as_of_date": {"type": "string", "description": "YYYY-MM-DD, mac dinh la hom nay"},
                "limit": {"type": "integer", "description": "So luong toi da tra ve, mac dinh 20"},
            },
            "required": [],
        },
    },
    {
        "name": "get_revenue_reconciliation",
        "description": "Doi chieu doanh thu OTC tinh TU TREN XUONG (tong hoa don toan vung) voi doanh "
                        "thu CONG DON TU DUOI LEN (TDV -> QLV -> TP, tu KPI ca nhan) - dung khi nguoi "
                        "dung hoi kieu 'so lieu nay co khop voi KPI nhan vien khong', 'doanh thu tong "
                        "co dung khong', 'kiem tra chieo doanh thu tu duoi len', hoac nghi ngo so lieu "
                        "tong the bi lech so voi tong hop tu cap duoi. Ket qua co 'coverage_pct' (cong "
                        "don duoc bao nhieu % so tong tren xuong) - THAP HON 100% la BINH THUONG (kenh "
                        "ETC + khach mo coi + cac 'to' chua xac dinh QLV khong the cong don duoc, xem "
                        "'note' trong ket qua), CHI canh bao that neu co truong 'warning' rieng (dau "
                        "hieu dem trung TDV).",
        "input_schema": {
            "type": "object",
            "properties": {
                "as_of_date": {"type": "string", "description": "YYYY-MM-DD, mac dinh la hom nay (lay snapshot KPI gan nhat truoc/bang ngay nay)"},
                "area_code": {"type": "string", "description": "Loc theo 1 vung MB/MT/MN (khong bat buoc - bo trong de doi chieu toan cong ty)"},
            },
            "required": [],
        },
    },
    # 10/08/2026: bo sung khoi "GOI DUNG 1 LAN LA DU" sau khi cau hoi "Bao cao chi phi AI chi tiet theo
    # nguoi dung" that bai 2 lan lien tiep trong 1 buoi (14:10 va 14:12, 2 phien khac nhau), nguoi dung
    # nhan cau tu choi "cau hoi qua phuc tap". Doc audit_log 2 phien do thay cung 1 khuon mau:
    #   vong 1: get_audit_log(target_username='all') -> DA co san user_breakdown (dnh, vui.hoangthi,
    #           diag_test) - tuc la da du de tra loi ngay tu day
    #   vong 2-4: goi LAI tool cho TUNG username mot, roi doi limit, roi quet sqlite_master tim bang
    #           chi phi khac -> can MAX_TOOL_ROUNDS, roi vao fallback
    # Nguyen nhan: audit_log_summary() CO Y tra user_breakdown=None khi loc 1 nguoi cu the (luc do bao
    # cao chi con 1 nguoi, tach ra khong con y nghia - xem report_templates.py ~2029). Model doc thay
    # null thi tuong bi loi/thieu quyen nen cang co thu them. Day KHONG phai loi du lieu va KHONG phai
    # do effort (da go 06/08) - chi la mo ta tool chua noi ro. Cach chua giong het get_salary_detail
    # ben duoi (cung benh: goi lap cho tung nguoi).
    {
        "name": "get_audit_log",
        "description": "Lich su truy van va token/chi phi AI quy doi VND/USD. Voi tai khoan C-Level hoac Admin: ho tro xem BÁO CÁO CHI PHÍ AI TOÀN CÔNG TY hoac loc theo nguoi dung (target_username). Voi tai khoan QLV/TDV: xem chi phi va lich su ca nhan. "
                        "GOI DUNG 1 LAN LA DU voi cac cau kieu 'chi phi AI chi tiet theo nguoi dung', "
                        "'ai ton bao nhieu tien', 'bao cao chi phi toan cong ty': MOT lan goi "
                        "target_username='all' DA tra ve san truong 'user_breakdown' - bang chi phi TACH "
                        "SAN theo TUNG tai khoan (so luot, so phien, token, USD, VND). Do CHINH LA phan "
                        "'chi tiet theo nguoi dung' ma nguoi hoi can, lay thang tu do ma trinh bay. "
                        "TUYET DOI KHONG goi lai tool nay rieng cho tung username de 'dao sau them', va "
                        "KHONG dung query_database/sqlite_master de tim nguon chi phi khac (khong co bang "
                        "nao khac) - lam vay chi ton token va tien, lai de cham tran so vong goi tool "
                        "khien ca cau hoi that bai. "
                        "LUU Y QUAN TRONG: khi loc DUNG 1 nguoi (target_username='<ten>') thi "
                        "'user_breakdown' CO Y tra ve null, vi luc do bao cao chi con 1 nguoi nen khong "
                        "con gi de tach - day KHONG PHAI loi, KHONG PHAI thieu quyen, KHONG duoc goi lai "
                        "de thu. Chi truyen ten cu the khi nguoi hoi dich danh DUNG 1 nguoi. "
                        "CACH TRINH BAY: ket qua co truong 'display_hint' - PHAI theo dung huong dan do "
                        "(dang TIMELINE, moi dong 1 su kien voi gio + event_summary DA SOAN SAN dung "
                        "nguyen van, moi nhat len dau, KHONG trinh bay thanh bang SQL/cot ky thuat).",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "So ngay gan nhat can xem, mac dinh 7"},
                "limit": {"type": "integer", "description": "So dong lich su gan nhat toi da tra ve, mac dinh 30"},
                "target_username": {"type": "string", "description": "Ten tai khoan nguoi dung can loc (chi danh cho C-Level/Admin), hoac 'all' de xem toàn cong ty. NEN dung 'all': ket qua da co san user_breakdown tach chi phi theo TUNG nguoi, KHONG can goi lai cho tung username. Chi truyen ten cu the khi nguoi hoi dich danh dung 1 nguoi."},
            },
            "required": [],
        },
    },
    {
        "name": "get_salary_achievement_summary",
        "description": "Bao cao tong hop/thong ke so luong nhan vien dat cac moc thuong tien do (V15, V22, V25) va ASO tren toan cong ty hoac toan doi cua QLV. "
                       "Dung khi nguoi dung hoi 'co bao nhieu nguoi dat V15', 'tong hop V22 toan quoc/toan doi', 'thong ke ASO', v.v. "
                       "Phan quyen: neu nguoi hoi la C-Level se thay toan bo, neu la QLV se tu dong bi gioi han ve doi cua minh. "
                       "Ve dieu kien ap dung V15/V22/V25 theo vai tro va quy tac snapshot CUOI KY (KHONG phai tien do "
                       "thang hien tai) - xem chi tiet o mo ta tool get_salary_detail, ap dung giong het o day.",
        "input_schema": {
            "type": "object",
            "properties": {
                "save_date": {
                    "type": "string",
                    "description": "Thang can tra cuu (YYYY-MM). Neu de trong se lay ky luong gan nhat.",
                },
                "scope_area_code": {
                    "type": "string",
                    "description": "Ma vung mien can tra cuu (MB, MT, MN, ...). Khong bat buoc.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_salary_detail",
        "description": "Chi tiet THUONG KINH DOANH + PHU CAP thang cua 1 nhan vien (V15/V22/V25 thuong "
                        "tien do, ASO, thuong danh muc DM1/DM2/DM3, SKU, khach tai don/khach moi), theo "
                        "chinh sach thu nhap moi (QD 0429/.25 Mien Nam/Trung, QD 0107/2026 TDV toan "
                        "quoc, hieu luc tu 28/07/2026) - dung khi nguoi dung hoi 'thuong thang nay cua "
                        "toi/cua [ten] bao nhieu', 'V15/V22/V25/ASO cua [ten]', 'thuong danh muc/tien do "
                        "cua toi', 'ket qua KPI luong cua toi'. "
                        "QUAN TRONG VE HIEU LUC: V15, V22 chi ap dung cho TDV. V25 chi ap dung cho Truong phong, Quan ly vung, Cho si, Kenh MT. "
                        "He thong chi luu snapshot luong CUOI KY (vd 30/06, 31/07). Neu user hoi tien do giua thang (vd 25/07), tool se tra ve cua "
                        "thang truoc do (30/06). KHI TRA LOI PHAI KET LUAN/NOI RO diem nay: 'He thong chi chot luong cuoi ky, day la ket qua luong thang truoc da chot, khong phai tien do thang nay'. "
                        "HOI NHIEU NGUOI CUNG LUC (vd 'V15/V22/V25/ASO cho ca 4 TDV cua QLV X', 'thuong "
                        "cua tat ca nhan vien vung Y') -> TRUYEN DANH SACH CAC MA NHAN VIEN PHAN CACH BANG DAU PHAY "
                        "(vd employee_code='MBKV1,MBKV2,MBKV3,MBKV4') TRONG DUNG 1 LAN GOI TOOL DUY NHAT. "
                        "TUYET DOI KHONG GOI TOOL NAY NHIEU LAN LAP LAI CHO TUNG NGUOI DE TIET KIEM TOKEN VA TIEN. "
                        "Neu 1 nguoi trong danh sach bi loi/tu choi (vd khong du quyen), ket qua se bao ro "
                        "nguoi do va ly do trong truong 'errors' - KHONG duoc im lang bo qua, phai neu ro "
                        "voi nguoi dung ai bi thieu va vi sao. "
                        "!!! CANH BAO QUAN TRONG: ket qua CHUA GOM Luong co ban (LCB) - he thong hien "
                        "CHUA co du lieu LCB (Bravo khong luu san muc LCB theo Level). PHAI noi ro voi "
                        "nguoi dung day la THUONG KINH DOANH + PHU CAP, KHONG PHAI 'tong luong'/'tong "
                        "thu nhap' day du - neu ho hoi tong thu nhap/luong thang, tra loi phan thuong "
                        "nay VA noi ro con thieu LCB, de nghi lien he ke toan/HR de biet LCB chinh xac. "
                        "PHAN QUYEN: mac dinh CHI tra ve DUNG cua nguoi dang hoi (server tu dong xac "
                        "dinh, KHONG the xem cua nguoi khac du truyen employee_code gi) - tai khoan "
                        "C-Level HOAC QLV (xem doi cua chinh minh) moi xem duoc nguoi khac qua tham so "
                        "employee_code; QLV Bui Khac Dung hoi ve 4 TDV cua chinh minh la HOP LE, KHONG "
                        "duoc tu choi truoc khi thu goi tool. Phan quyen AP DUNG RIENG cho TUNG nguoi "
                        "trong danh sach, khong noi long chi vi goi hang loat.",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_code": {"type": "string", "description": "Ma/ten nhan vien can tra cuu - co the truyen NHIEU ma cach nhau bang dau phay (vd 'MBKV1,MBKV2,MBKV3') de tra ve ca danh sach trong 1 lan goi. CHI co hieu luc voi tai khoan C-Level/QLV xem doi minh, bi bo qua voi tai khoan thuong (tu dong dung chinh nguoi hoi)"},
                "save_date": {"type": "string", "description": "YYYY-MM-DD, mac dinh la snapshot moi nhat hien co (thuong cuoi thang/dot chot gan nhat)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_salary_ranking",
        "description": "Xep hang TOP N nhan vien co THUONG CAO NHAT (hoac thuong V15, V22, V25, ASO, Thuong danh muc DM) "
                        "trong ky/thang. DUNG KHI HOI 'top 30 nhan vien duoc thuong nhieu nhat', 'top thuong MB', "
                        "'ai duoc thuong V15 cao nhat', 'danh sach top thuong thang 7', 'top 10 thuong mien bac', "
                        "'top 30 theo MB', 'tong thuong luon'. "
                        "Tra ve bang xep hang day du (thuong total, V15, V22, V25, ASO, allowance, % target) "
                        "chay sieu toc trong 0.01 giay. TUYET DOI KHONG dung SQL ad-hoc hoac tool khac cho nhu cau nay.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year_month": {"type": "string", "description": "Thang/ky can xem (YYYY-MM hoac YYYY-MM-DD, vd '2026-07')"},
                "area_code": {"type": "string", "description": "Ma vung mien loc (MB, MT, MN, hoac bo trong neu xem toan quoc)"},
                "position_code": {"type": "string", "description": "Chuc danh loc (TDV, QLV, TP, TK, hoac bo trong). TP = Truong phong = Giam doc Mien = Giam doc Kenh (cap quan ly mien/kenh). TK = Truong kenh = Truong kenh MT (Modern Trade) - cap QLV, KHONG phai TP. CS = Cho si - cung cap QLV."},
                "bonus_type": {"type": "string", "enum": ["total", "v15", "v22", "v25", "aso", "dm"], "description": "Loai thuong quan tam: 'total' (tong thuong KD), 'v15', 'v22', 'v25', 'aso', 'dm' (thuong danh muc)"},
                "limit": {"type": "integer", "description": "So luong nhan vien muon lay (mac dinh 30, toi da 100)"}
            },
            "required": [],
        },
    },
]

QUERY_TOOL = {
    "name": "query_database",
    "description": (
        "CHI dung cho cau hoi AD-HOC ve hoa don/doanh thu/san pham/khach hang/nhan vien/vung mien/"
        "tra hang KHONG thuoc bat ky tool bao cao chuan nao o tren (vd dieu kien loc dac thu...). "
        "Chay 1 cau SQL SELECT (chi doc) tren kho 'local' (SQLite, dong bo dinh ky tu Bravo, co day "
        "du lich su - dung LIMIT N, KHONG dung TOP N, KHONG can quote ten cot). "
        "Chi duoc dung SELECT/WITH, khong duoc INSERT/UPDATE/DELETE/DROP/ALTER."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "Cau lenh SQL SELECT (dialect SQLite) can chay tren kho local"},
            "explanation": {"type": "string", "description": "Giai thich ngan gon muc dich cau query nay"},
        },
        "required": ["sql"],
    },
}

QUERY_SUPABASE_TOOL = {
    "name": "query_inventory_receivables",
    "description": (
        "CHI dung cho cau hoi ve TON KHO (inventory) - du lieu do dong nghiep tu nhap tren Supabase. "
        "CONG NO KHONG dung tool nay nua (da chuyen sang bang fact_congno_khachhang o kho local - dung "
        "query_database). Chay 1 cau SQL SELECT (chi doc) tren Supabase (PostgreSQL - ten cot phan biet "
        "hoa/thuong, PHAI dat trong dau ngoac kep \"...\"). Chi duoc dung SELECT/WITH, khong INSERT/UPDATE/DELETE/DROP."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "Cau lenh SQL SELECT (PostgreSQL) can chay tren Supabase"},
            "explanation": {"type": "string", "description": "Giai thich ngan gon muc dich cau query nay"},
        },
        "required": ["sql"],
    },
}

SAVE_GLOSSARY_TOOL = {
    "name": "save_business_term",
    "description": "Luu 1 thuat ngu nghiep vu ma NGUOI DUNG vua dinh nghia trong cau hoi hien tai (vd "
                    "'doanh thu rong nghia la doanh thu tru chiet khau') de cac lan hoi sau tu dong ap "
                    "dung dung nghia nay, khong can nguoi dung giai thich lai. CHI goi khi nguoi dung "
                    "THUC SU dang dinh nghia 1 khai niem (khong phai chi hoi so lieu binh thuong).",
    "input_schema": {
        "type": "object",
        "properties": {
            "term": {"type": "string", "description": "Ten thuat ngu, vd 'doanh thu rong'"},
            "definition": {"type": "string", "description": "Dinh nghia nguoi dung vua giai thich"},
        },
        "required": ["term", "definition"],
    },
}

RAW_SQL_TOOLS = {"query_database": "local", "query_inventory_receivables": "supabase"}
LOCAL_UTIL_TOOLS = REALTIME_TOOL_NAMES | {"save_business_term"}

ALL_TOOLS = TEMPLATE_TOOLS + [QUERY_TOOL, QUERY_SUPABASE_TOOL] + REALTIME_TOOLS + [SAVE_GLOSSARY_TOOL]
# Tools KHONG bao gio doi trong 1 phien chay - danh cache_control tren tool CUOI CUNG de cache ca
# mang tools (Anthropic cache theo kieu "prefix": danh dau 1 block = cache moi thu TINH DEN block do).
ALL_TOOLS_CACHED = ALL_TOOLS[:-1] + [{**ALL_TOOLS[-1], "cache_control": {"type": "ephemeral", "ttl": "1h"}}]

# Beta header can thiet de dung TTL 1h (mac dinh cache_control chi song 5 phut neu khong co header nay).
# Ap dung cho toan bo request (system + tools) - giup cache song qua nhieu cau hoi lien tiep trong gio
# hanh chinh thay vi het han sau vai phut, tang ty le cache-hit (chi ~10% gia input goc khi hit).
_CACHE_BETA_HEADERS = {"anthropic-beta": "extended-cache-ttl-2025-04-11"}


def _static_system_prompt() -> str:
    """Phan TINH cua system prompt (quy tac + schema) - KHONG bao gio doi giua cac lan goi, nen danh
    cache_control (TTL 1h) o day. Moc ngay du lieu ("hom nay") la phan DONG, tach rieng o
    _dynamic_context_note() de khong lam vo cache moi 15-30 phut khi kho dong bo lai."""
    return f"""Ban la AI Analyst chuyen phan tich du lieu kinh doanh cho Duoc Nam Ha (DNH),
mot doanh nghiep duoc pham. Nguoi dung se hoi bang tieng Viet ve doanh thu, cong no, KPI nhan vien,
ton kho, vung mien... Ban dung cac tool duoc cung cap de truy van du lieu THAT tu Data Warehouse
roi tra loi dua tren ket qua thuc te - KHONG duoc bia so lieu.

Neu cuoc hoi thoai co cac luot truoc do, HAY DUNG NGU CANH DO de hieu cau hoi hien tai (vd neu vua
hoi "doanh thu thang 6" roi hoi tiep "con thang 5?", hieu la van hoi doanh thu theo kenh/tieu chi
tuong tu nhung doi sang thang 5) - KHONG hoi lai nguoi dung nhung gi da ro tu ngu canh truoc.

QUAN TRONG VE CHON TOOL:
- ⚠️  KHONG BAO GIO nhac ten tool/ham/truong ky thuat trong cau tra loi cho nguoi dung. Nguoi doc la
  lanh dao kinh doanh, khong phai lap trinh vien. VD SAI: "tra cuu chi tiet (get_customer_detail)",
  "count_full_target = 0", "[tien ich] resolve_relative_date(...)". VD DUNG: "toi co the tra cuu chi
  tiet tung khach hang de xem ai phu trach". Mo ta viec lam bang ngon ngu nghiep vu, giau het ten ky
  thuat ben trong.
- Neu cau hoi thuoc 1 trong 17 nhom: doanh thu theo kenh, top san pham, top khach hang, doanh thu
  theo vung mien, KPI/doanh so nhan vien (tong quan/thang), KPI THEO NGAY 1 nhan vien ca nhan, SO SANH
  2 khoang thoi gian, CHI TIET 1 khach hang cu the, TRA CUU ma/ten/vai tro nhan vien, KIEM TRA don hang
  bat thuong/chay don KPI, TON KHO THEO VUNG, LICH SU DOI QLV, CAY DOANH THU/KPI TP-QLV-TDV, XEP HANG
  KPI, DOI CHIEU doanh thu tu tren xuong vs cong don tu duoi len, LICH SU TRUY VAN/CHI PHI AI cua chinh
  nguoi dang hoi, THUONG KINH DOANH/PHU CAP thang cua 1 nhan vien -> BAT BUOC dung tool tuong ung
  (get_revenue_by_channel, get_top_products, get_top_customers, get_revenue_by_region, get_employee_kpi,
  get_employee_daily_kpi, compare_periods, get_customer_detail, get_employee_directory, check_order_timing,
  get_inventory_by_region, get_qlv_change_history, get_revenue_tree, get_kpi_ranking,
  get_revenue_reconciliation, get_receivables_overview, get_audit_log, get_salary_detail,
  get_salary_achievement_summary).
- DU BAO DOANH THU CA THANG: dung get_revenue_forecast (khong phai tinh tay). Khi trinh bay ket qua
  BAT BUOC lam du 3 dieu, thieu 1 la sai:
  (1) noi ro DAY LA UOC TINH, khong phai doanh thu thuc te;
  (2) neu kem KHOANG uoc tinh + sai so trung binh ma tool tra ve, KHONG duoc rut gon thanh 1 con so;
  (3) neu la thang dang chay, phan biet ro so LUY KE THUC TE den nay voi so UOC TINH ca thang.
  Mo hinh chi dua tren mua vu lich su, KHONG biet su kien moi (mat khach lon, thau ETC, dut hang) -
  neu nguoi dung nhac toi su kien nhu vay thi phai noi ro con so nay chua tinh den.
  Neu tool tra ve "ly_do_khong_du_bao" (thieu lich su) thi NOI THANG la khong du bao duoc cho pham vi
  do va noi ly do - TUYET DOI KHONG tu bia so thay the.
  Ngoai tool nay ra, TUYET DOI KHONG tu suy ra con so du bao bang cach chia ty le hay ngoai suy tu
  du lieu luy ke (vd lay luy ke chia so ngay roi nhan so ngay ca thang) - doanh thu DNH don ve cuoi
  thang nen cach do sai rat nang.
  Day la cac truy van DA DUOC KIEM CHUNG khop voi du lieu goc, KHONG tu sinh SQL thay the.
- Neu cau hoi co NHIEU khia canh cung luc (vd hoi ca doanh thu, top san pham, vung mien, nhan vien
  trong 1 cau) -> goi TUAN TU nhieu tool tuong ung, moi tool 1 khia canh, roi tong hop lai.
- CONG NO: cau hoi TONG HOP/nhieu khach (tong no qua han, top khach no, ty le qua han theo vung/kenh)
  -> dung get_receivables_overview. Cong no cua 1 khach cu the -> get_customer_detail. CONG NO da
  KHONG con tren Supabase - TUYET DOI khong truy van receivable_detail/receivable_etc (bang cu, da chan).
- Voi phan cau hoi KHONG thuoc cac nhom tren: neu la ve TON KHO (inventory) -> dung
  query_inventory_receivables (Supabase). Con lai (hoa don/doanh thu/san pham/khach hang/nhan vien/vung
  mien ad-hoc, tra hang...) -> dung query_database (kho local SQLite). Neu can boc tach cong no ad-hoc
  ngoai 2 tool cong no tren, dung query_database tren bang fact_congno_khachhang (LUON SUM theo khach).
- Cau hoi CO cum tu thoi gian TUONG DOI (hom nay, tuan nay, thang truoc, quy nay, quy truoc, cung ky
  nam ngoai, N thang/ngay gan nhat...) -> BAT BUOC goi resolve_relative_date TRUOC de lay khoang ngay
  cu the, roi moi dung ket qua do lam date_from/date_to cho tool khac - TUYET DOI KHONG tu suy luan
  ngay thang, de tranh nham quy/thang. Neu resolve_relative_date bao loi (khong nhan dien duoc cum
  tu), hoi lai nguoi dung ngay/khoang ngay cu the thay vi doan bua.
- Neu nguoi dung dinh nghia 1 thuat ngu nghiep vu moi trong cau hoi (vd "doanh thu rong la doanh thu
  tru chiet khau") -> goi save_business_term de luu lai, roi tiep tuc tra loi cau hoi nhu binh thuong.
- Voi KPI nhan vien TONG QUAN/xep hang/nhieu nhan vien cung luc (ke ca ma khu vuc nhu MBKV*, ASM*):
  dung get_employee_kpi. CO BA MOC KHAC NHAU, TUYET DOI KHONG GOP - va dung goi moc 65%/70% la
  "dat chi tieu" HAY "dat KPI": do chi la cong BAT DAU DUOC HUONG THUONG NHOM HANG.
    - Hoi "ai chua dat chi tieu / bao nhieu nguoi dat chi tieu" -> dung "count_full_target" (moc 100%).
      Giua thang con so nay gan nhu luon ~0 va DO LA DUNG, khong phai loi: doanh so moi luy ke toi hom
      nay con chi tieu la ca thang. Noi ro dieu do thay vi de nguoi doc tuong he thong hong.
    - Hoi "ai dat KPI / bao nhieu nguoi dat KPI" -> dung "count_kpi_achieved" (moc 80%, truong
      "kpi_threshold_pct"), AP DUNG CHUNG cho moi vai tro. Day cung la moc quyet dinh mau 🟢/🟡/🔴.
    - Hoi "ai toi muc thuong nhom hang" -> dung "count_above_target"/"count_below_target", nguong lay
      tu truong "threshold" cua tung dong (TDV 65% theo QD 0107/2026, QLV va cac cap quan ly 70% theo
      QD 0429/.25 - van hieu luc voi cap quan ly).
    - Nguoi dat 67%: dien dat dung la "da toi muc thuong nhom hang (65%) nhung CHUA dat KPI (80%)".
    - Cau hoi mo ho -> dua CA BA con so kem nhan ro rang, dung tu chon 1 cai roi im lang.
    - KHONG bao gio in ten truong ky thuat ra cho nguoi dung (vd dung viet "count_full_target = 0").
      Nguoi doc la lanh dao kinh doanh, khong phai lap trinh vien - noi "0/87 nguoi dat chi tieu".
  ⚠️ 65%/70% CHI la cong cua THUONG NHOM HANG (DM1/DM2/DM3). DNH con it nhat 5 ho thuong khac, moc
  khac va tra theo CHI SO KHAC: V15 (dat 25% doanh so thang vao ngay 15), V22 (55% + ty le target
  >=75/80%), V25 (>=70% tinh den ngay 25), ASO (theo SO LUONG khach hang hoat dong: MB 40 / MT 35 /
  MN 25 - KHONG phai %), thuong quy (>=80% quy), thuong nam (>=75% nam). Luong co ban: tu 60% tro len
  van huong 100%, duoi 60% moi bi cat ty le. => Nguoi duoi 65% VAN CO THE duoc V15/ASO va VAN huong
  du luong co ban. TUYET DOI KHONG duoc dien dat thanh "khong duoc thuong", "khong dat KPI", "bi cat
  thuong" - do la noi SAI ve tien luong cua nguoi that. Chi duoc noi dung pham vi: "chua toi muc
  thuong nhom hang". He thong hien CHUA co du lieu de tinh V15/V22/ASO nen KHONG duoc suy doan ho co
  duoc cac khoan do hay khong.
  Truong "status" (🟢 Tot / 🟡 Trung binh / 🔴 Nguy hiem) chia theo moc DAT KPI 80% (KHONG phai muc
  huong thuong 65/70%) - LUON dat emoji nay canh ten/ma NV, khong tu nghi nguong khac. Vi du dung:
  "QLV Nguyen Van A dat 67% chi tieu - da toi muc huong thuong nhom hang (70%) nhung CHUA dat KPI
  (80%), va con cach xa moc dat chi tieu 100%".
- Voi KPI THEO NGAY cua 1 nhan vien CA NHAN cu the trong 1 thang (vd "hieu suat hang ngay cua tungtx
  thang 7", "ngay nao tungtx do KPI") -> dung get_employee_daily_kpi. Nguong theo NGAY khac hoan toan
  nguong thang: 🔴 Do <2.5%, 🟡 Vang 2.5%-3.5%, 🟢 Xanh >3.5% (target ngay = 4% MonthSaleTarget). Tool
  nay KHONG dung duoc cho ma khu vuc/quan ly vung.
- Voi 1 khach hang CU THE (biet ma khach hang, hoi doanh thu/cong no/ai phu trach...) -> dung
  get_customer_detail. Ket qua co san "position_label" (vd "Trinh duoc vien"/"Quan ly vung") cho biet
  VAI TRO cua nhan vien phu trach - LUON neu ro vai tro nay khi tra loi. Khach hang kenh ETC thuan tuy
  se KHONG co nhan vien phu trach (employee_code/employee_name/position_label rong) - day la HAN CHE DU
  LIEU THUC TE (ETC khong co truong nay tren Bravo), KHONG phai loi, giai thich ro cho nguoi dung neu gap.

{SCHEMA_CONTEXT}

- TIET KIEM TOKEN VA TOC DO: VOI BAT KY TOOL NAO (get_salary_detail, get_customer_detail, get_employee_daily_kpi...), KHI CAN XEM NHIEU DOI TUONG (NHIEU NV, NHIEU KHACH HANG) -> TRUYEN DANH SACH CAC MA PHAN CACH BANG DAU PHAY (vd employee_code='NV1,NV2,NV3', customer_code='KH1,KH2,KH3') TRONG DUNG 1 LAN GOI TOOL DUY NHAT. TUYET DOI KHONG GOI TOOL MULTI-ROUNDS TAP LAP LAI DANG LE RA DUNG BANG BULK.

QUAN TRONG VE DO DAI CAU TRA LOI (tiet kiem chi phi - moi token output deu tinh tien):
- Tra loi NGAN GON, DI THANG vao so lieu - KHONG mo dau dai dong, KHONG nhac lai cau hoi, KHONG giai
  thich lai nhung gi tool da tra ve neu nguoi dung khong hoi "tai sao"/"giai thich".
  neu chi 1 con so thi neu ro con so + don vi + ngu canh (vd "ngay nao", "khach hang nao") trong 1-2 cau,
  KHONG viet thanh doan van dai. Neu ket qua co nhieu dong, dung BANG (markdown table) thay vi mo ta
  bang loi van. Chi mo rong nhan xet/phan tich khi nguoi dung hoi ro "vi sao"/"nhan xet"/"danh gia".
- Neu tool tra ve loi hoac khong co du lieu phu hop, noi ngan gon cho nguoi dung, khong doan bua.

TIET KIEM TOKEN - QUAN TRONG:
- Sau khi nhan du lieu tu tool, TRA LOI NGAY cho nguoi dung. Chi goi THEM tool khi: (a) tool truoc bao
  LOI/khong co du lieu can thu lai, hoac (b) cau hoi co NHIEU khia canh rieng biet can tool KHAC LOAI.
- TUYET DOI KHONG goi lai CUNG tool voi tham so tuong tu chi de "kiem tra lai" hay "xac nhan".
- Du lieu tra ve tu tool co the bi cat bot (neu qua dai) nhung DA DU de tra loi - khong can query lai.
"""


# Cac tool nhan DANH SACH ma ngan cach bang dau phay -> nhieu lenh goi trong CUNG mot luot co the gop
# lam mot, tiet kiem token. Gia tri = ten tham so chua ma. CHI duoc them tool vao day khi tool do THAT
# SU co tham so nay VA ham xu ly biet tach chuoi "A,B,C" - xem get_salary_detail lam mau.
# CANH BAO (10/08/2026): da tung co nguoi dinh them "get_employee_kpi": "employee_code" - SAI, tool do
# khong he co tham so employee_code (chi co as_of_date/limit/order_by/filter/position_code). Them nham
# se lam moi lenh goi thu 2 tro di cua tool do bi bo trong im lang.
BULK_TOOLS_MAP = {
    "get_salary_detail": "employee_code",
    "get_customer_detail": "customer_code",
    "get_employee_daily_kpi": "employee_code",
}


def _merge_bulk_tool_calls(tool_uses, bulk_tools_map=None):
    """Gop nhieu lenh goi CUNG mot tool trong CUNG mot luot thanh mot lenh goi duy nhat mang danh sach
    ma ngan cach bang dau phay. Tra ve tap id cua cac lenh goi DA BI GOP vao lenh khac (caller phai
    tra ve tool_result gia cho chung de giu dung hop dong cua Anthropic API).

    SUA 10/08/2026 - VA HAI LOI GAY MAT DU LIEU AM THAM. Ban cu (nam lan trong ask()) lam the nay:

        if codes:
            ... gop ...
        for sub in tu_list[1:]:        # <-- NAM NGOAI khoi `if codes:`
            merged_sub_ids.add(sub.id)

    1. DANH DAU "da gop" KE CA KHI KHONG GOP DUOC GI. Khi tool khong co tham so khoa (vd bi them nham
       vao bang), `codes` rong nen khong gop gi ca, NHUNG cac lenh goi thu 2 tro di van bi danh dau va
       bi bo. Model nhan lai dung cau "Da gop ket qua tra cuu hang loat vao luot goi truoc" - mot loi
       noi doi - roi tra loi tu tin bang du lieu thieu.
    2. CHI GOP MOT THAM SO KHOA, AM THAM VUT MOI THAM SO KHAC. Hoi "so sanh doanh so khach X thang 7
       voi thang 8" -> model goi get_customer_detail 2 lan CUNG customer_code nhung KHAC date_from/
       date_to. Sau khu trung, codes chi con ['X'], lenh goi thu 2 bi bo -> model chi co thang 7 nhung
       tuong da co ca hai.

    Cach sua: gom cac lenh goi theo "van tay" = toan bo tham so NGOAI khoa gop. Chi gop trong cung mot
    nhom (tuc la moi thu khac deu giong het, chi khac moi ma). Va chi danh dau da-gop khi THUC SU gop.
    Khac tham so -> de chay rieng, tha ton them mot luot con hon tra so thieu ma khong ai biet.
    """
    if bulk_tools_map is None:
        bulk_tools_map = BULK_TOOLS_MAP

    merged_sub_ids = set()
    tool_by_name = defaultdict(list)
    for tu in tool_uses:
        tool_by_name[tu.name].append(tu)

    for name, tu_list in tool_by_name.items():
        if name not in bulk_tools_map or len(tu_list) <= 1:
            continue
        param_name = bulk_tools_map[name]

        # Van tay: moi tham so TRU khoa gop. json.dumps de gia tri dict/list cung so sanh duoc
        # (tham so cua tool khong phai luc nao cung la chuoi/so).
        groups = defaultdict(list)
        for tu in tu_list:
            fingerprint = tuple(sorted(
                (k, json.dumps(v, sort_keys=True, ensure_ascii=False, default=str))
                for k, v in (tu.input or {}).items() if k != param_name
            ))
            groups[fingerprint].append(tu)

        for grp in groups.values():
            if len(grp) <= 1:
                continue
            codes = []
            for sc in grp:
                val = ((sc.input or {}).get(param_name) or "")
                val = val.strip() if isinstance(val, str) else str(val).strip()
                if val and val not in codes:
                    codes.append(val)
            if not codes:
                # Khong lay duoc ma nao -> tool nay khong co tham so khoa (bi them nham vao bang).
                # TUYET DOI khong danh dau da-gop o day - de tat ca chay binh thuong. Day chinh la
                # loi (1) neu tren: ban cu van danh dau, khien lenh goi thu 2 bi bo trong im lang.
                continue
            # Den day: cung tool, cung moi tham so phu, chi khac ma (hoac trung hoan toan) -> gop
            # an toan. codes co 1 phan tu nghia la cac lenh goi trung het nhau, gop lai la dung.
            primary = grp[0]
            merged_input = dict(primary.input or {})
            merged_input[param_name] = ",".join(codes)
            primary.input = merged_input
            for sub in grp[1:]:
                merged_sub_ids.add(sub.id)

    return merged_sub_ids


def _dynamic_context_note(question: str = "", session_id: str = "", scope_area_code: str = None,
                           scope_employee_code: str = None, scope_channel: str = None) -> str:
    """Phan DONG cua system prompt (ngay du lieu + ngu canh doi theo tung cau hoi) - tach rieng khoi
    phan tinh de KHONG lam vo cache (kho local dong bo lai moi 15-30 phut, glossary/query-state doi
    theo tung cau hoi nen KHONG the cache chung voi schema/rules tinh)."""
    latest = latest_data_date()
    parts = [f'Ngay co du lieu moi nhat trong kho hien tai: {latest} (dung lam moc cho "hom nay"/'
             f'"gan day" neu nguoi dung khong noi ro ngay; kho local co the tre toi da ~15-30 phut so voi Bravo that).']

    # 10/08/2026: sync_freshness_note() da co san day du logic (report_templates.py) tu truoc nhung
    # CHUA TUNG duoc goi o dau ca - phat hien khi doi chieu mot ban "Technical Spec" voi code that.
    # No tu tra chuoi RONG khi moi thu binh thuong (khong lam nhieu prompt vo co), chi len tieng khi
    # tien trinh sync co dau hieu TREO qua 60 phut. Neu sang demo 13/08 sync chet ma khong ai biet,
    # day la cach chatbot TU NOI RA thay vi lang le tra so cu nhu the la so moi.
    freshness = sync_freshness_note()
    if freshness:
        parts.append(freshness)

    if scope_area_code:
        parts.append(
            f'QUAN TRONG - TAI KHOAN NAY BI GIOI HAN VUNG {scope_area_code}: moi tool bao cao da duoc '
            f'EP LOC theo dung vung nay o tang he thong (khong the vo tinh lo du lieu vung khac du AI '
            f'co lam gi). Neu nguoi dung hoi ve 1 vung KHAC (vd hoi "mien Nam" trong khi tai khoan chi '
            f'duoc xem {scope_area_code}), hoac hoi CHUNG CHUNG kieu "ca cong ty"/"toan quoc" - PHAI TU '
            f'CHOI RO RANG, giai thich tai khoan chi co quyen xem vung {scope_area_code}, KHONG duoc tra '
            f'loi bang so lieu vung {scope_area_code} nhu the la dung cau hoi (gay hieu nham). Tool tra '
            f'cuu SQL tu do (query_database) KHONG kha dung cho tai khoan nay. '
            f'MOI cau tra loi co so lieu (ke ca khi nguoi dung KHONG hoi ro vung) PHAI ghi ro dang "(vung '
            f'{scope_area_code})" ngay canh con so - de nguoi dung luon biet day la so lieu da bi gioi han '
            f'vung, khong phai so lieu toan quoc/vung khac.'
        )
    if scope_employee_code:
        parts.append(
            # 23/07/2026: PHAI noi ro AI dang phuc vu AI - truoc day note nay khong he cho biet ma nhan
            # vien cua chinh nguoi dung, nen khi ho hoi "doi TOI co ai chua dat chi tieu" thi AI khong
            # biet "toi" la ai va HOI NGUOC LAI xin ma nhan vien, du he thong DA tu ep loc dung doi ho.
            # Nguoi dung phai tu khai ma nhan vien cua chinh minh la trai nghiem rat te (va ho thuong
            # khong nho ma).
            f'BAN DANG PHUC VU TAI KHOAN CUA QUAN LY VUNG (QLV) CO MA NHAN VIEN "{scope_employee_code}". '
            f'Khi nguoi dung noi "toi"/"doi toi"/"nhan vien cua toi", ho dang noi ve chinh QLV nay va '
            f'doi TDV duoi quyen ho. TUYET DOI KHONG hoi nguoc lai xin ma nhan vien cua ho - he thong '
            f'DA biet va DA tu dong gioi han moi bao cao ve dung doi cua ho o tang code. Cu goi tool '
            f'binh thuong, ket qua tra ve DA duoc loc san. '
            # 23/07/2026: truoc day chi liet ke 2 tool; nay moi bao cao hieu suat theo tung nguoi deu bi
            # gioi han theo doi (xem _PERSON_LEVEL_TEMPLATES trong report_templates.py).
            # 10/08/2026: bo get_kpi_forecast_model1 khoi danh sach nay. Cau tren khang dinh cac tool
            # nay "deu CHI tra ve du lieu CUA CHINH DOI HO", nhung forecast_model1() nhan
            # scope_area_code/scope_employee_code roi KHONG DUNG, va cung khong nam trong
            # _PERSON_LEVEL_TEMPLATES/_EMPLOYEE_SCOPED_TEMPLATES nen tang code cung khong chan ho.
            # Tuc la prompt dang hua mot dang, code lam mot neo. Tool da bi go hAn (xem ghi chu o
            # TEMPLATE_TOOLS), nhung ke ca khi bat lai cung KHONG duoc dua vao day truoc khi that su
            # co co che gioi han theo doi.
            f'MOI bao cao hieu suat theo tung nguoi (get_employee_kpi, get_employee_daily_kpi, '
            f'get_revenue_tree, get_kpi_ranking) deu CHI tra ve du lieu CUA CHINH DOI HO - khong thay '
            f'ten/so lieu KPI ca nhan cua QLV khac hay TDV doi khac trong cung vung '
            f'{scope_area_code or ""} - day la du lieu hieu suat nhay cam cua dong nghiep, khac voi so '
            f'lieu doanh thu/ton kho tong hop thong thuong. '
            f'Neu nguoi dung hoi "so sanh voi QLV khac" hoac "QLV nao tot nhat vung", PHAI TU CHOI ro '
            f'rang phan so sanh voi nguoi khac, chi dua duoc so lieu cua chinh ho. '
            f'Mot so bao cao (vd check_order_timing) bi CHAN han voi tai khoan nay - neu tool tra ve loi '
            f'noi vay thi giai thich lai cho nguoi dung, dung tim cach lach bang tool khac.'
        )
    if scope_channel:
        parts.append(
            f'QUAN TRONG - TAI KHOAN NAY BI GIOI HAN KENH {scope_channel}: moi tool bao cao da duoc EP '
            f'LOC chi tra ve du lieu kenh {scope_channel} o tang he thong (ETC/kenh khac se KHONG xuat '
            f'hien trong ket qua du AI co lam gi). Neu nguoi dung hoi RO RANG ve kenh khac (vd hoi "ETC" '
            f'trong khi tai khoan chi duoc xem {scope_channel}), hoac hoi CHUNG CHUNG kieu "ca 2 kenh"/ '
            f'"tat ca kenh" - PHAI TU CHOI RO RANG, giai thich tai khoan chi co quyen xem kenh {scope_channel}, '
            f'KHONG duoc tra loi bang so lieu kenh {scope_channel} nhu the la du du lieu (gay hieu nham la '
            f'da bao gom ca kenh kia). Tool tra cuu SQL tu do (query_database/query_inventory_receivables) '
            f'KHONG kha dung cho tai khoan nay. MOI cau tra loi co so lieu doanh thu/don hang PHAI ghi ro '
            f'dang "(chi kenh {scope_channel})" ngay canh con so.'
        )

    glossary = retrieve_relevant_glossary(question)
    if glossary:
        parts.append("Dinh nghia nghiep vu nguoi dung da giai thich truoc do, ap dung neu lien quan:\n"
                      + "\n".join(f"- {g}" for g in glossary))

    if session_id:
        qs = get_query_state(session_id)
        if qs and qs.get("last_tool"):
            parts.append(f'Ngu canh truy van GAN NHAT trong phien nay: da dung {qs["last_tool"]}'
                          f'({qs["last_args"]}) - neu cau hoi hien tai la hoi tiep kieu "con...thi sao",'
                          f' "so voi..." thi dung lam diem tham chieu.')

    examples = retrieve_similar_examples(question)
    if examples:
        ex_text = "\n".join(f"- Cau hoi: {e['question']}\n  SQL: {e['sql']}" for e in examples)
        parts.append("Vi du cau hoi-SQL tuong tu tung chay thanh cong truoc do (chi de THAM KHAO cach "
                      "viet, KHONG copy may moc neu cau hoi hien tai khac ve dieu kien loc):\n" + ex_text)

    return "\n\n".join(parts)


def ask(question: str, session_id: str = "default", username: str = None, scope_area_code: str = None,
        scope_employee_code: str = None, scope_channel: str = None, scope_role: str = None) -> dict:
    """
    Nhan cau hoi tieng Viet + session_id (1 phien chat webapp) - tu dong nho lai vai cau hoi/tra loi
    gan nhat trong CUNG session de hieu ngu canh cau hoi tiep theo.
    scope_area_code: NEU duoc truyen (tai khoan regional_director/qlv bi gioi han vung), MOI tool bao
    cao chuan se bi EP LOC theo dung vung nay o TANG CODE (report_templates.py), va tool SQL tu do
    (query_database/query_inventory_receivables) se bi LOAI HAN khoi danh sach tool kha dung - day la
    lop bao ve du lieu THAT (khong phu thuoc AI co lam dung huong dan hay khong).
    scope_employee_code: CHI danh cho tai khoan qlv - gioi han rieng cac bao cao lo hieu suat CA NHAN
    dong nghiep (get_revenue_tree/get_kpi_ranking) chi con doi cua rieng ho, khong thay KPI ca nhan
    cua cac QLV khac trong cung vung (khac scope_area_code van cho xem so lieu TONG HOP ca vung o cac
    tool khac nhu doanh thu/ton kho - 2 co che tach biet, xem main.py).
    scope_channel: doc lap voi 2 co che tren - CHI gioi han theo kenh (vd 'OTC') khi tai khoan duoc gan
    rieng, EP LOC tang code giong scope_area_code, cung LOAI HAN tool SQL tu do (vi khong loc kenh duoc
    o SQL tu do).
    Tra ve dict: {answer: str, sql_used: [list mo ta cac tool/SQL da chay], last_result: {...} hoac None}
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key == "mock-key-for-local-testing":
        return {
            "answer": "⚠️ **Chưa cấu hình API Key Claude/Anthropic**: Vui lòng bổ sung biến `ANTHROPIC_API_KEY=sk-ant-api03...` vào file `backend/.env` để khởi chạy tính năng Phân tích Dữ liệu AI.",
            "sql_used": [],
            "last_result": None
        }

    client = anthropic.Anthropic(api_key=api_key)
    history = load_history(session_id, max_turns=MAX_HISTORY_TURNS)
    messages = list(history) + [{"role": "user", "content": question}]
    # Breakpoint cache thu 3 (ngoai tools + system tinh) - danh dau cuoi khoi tool_result MOI NHAT
    # de cache duoc ca lich su + tool_result cua cac vong truoc, khong bi tinh lai gia day du moi
    # vong. Chi giu 1 marker "dang hoat dong" tai 1 thoi diem (xoa marker vong truoc khi dat vong
    # moi) de khong vuot qua 4 breakpoint/request; cache server-side van doc duoc prefix da ghi tu
    # vong truoc nho co che nhin lui 20 block, khong can giu marker cu.
    # LUU Y breakpoint nay dung TTL MAC DINH (5 phut), khac 2 breakpoint kia dung "1h" - ly do day du
    # o cho dat cache_control trong vong lap ben duoi.
    _last_msg_cache_block = None

    sql_used = []
    last_result = None
    last_tool_used = None  # (name, args_str) - cap nhat query_state cuoi ham neu tra loi thanh cong
    ran_adhoc_query = None  # (question, sql) - luu vao longterm_memory neu query_database chay ok

    # Tai khoan bi gioi han vung: loai han tool SQL tu do khoi danh sach gui cho AI (AI KHONG CO KHA
    # NANG goi, khong chi la "duoc dan dung goi") - chi con lai cac tool bao cao chuan da kiem soat
    # duoc filter vung o tang code.
    tools_for_request = ALL_TOOLS_CACHED
    if scope_area_code or scope_channel:
        scoped_tools = [t for t in ALL_TOOLS if t["name"] not in RAW_SQL_TOOLS]
        tools_for_request = scoped_tools[:-1] + [{**scoped_tools[-1], "cache_control": {"type": "ephemeral", "ttl": "1h"}}]

    # System tach 2 block: block TINH (rules+schema) danh cache_control TTL 1h - it doi nen cache-hit
    # cao, chi tinh ~10% gia input goc; block DONG (ngay du lieu, glossary, query-state, few-shot, scope)
    # KHONG cache vi doi theo tung cau hoi/tai khoan.
    system_blocks = [
        {"type": "text", "text": _static_system_prompt(), "cache_control": {"type": "ephemeral", "ttl": "1h"}},
        {"type": "text", "text": _dynamic_context_note(question, session_id, scope_area_code, scope_employee_code, scope_channel)},
    ]

    # 06/08/2026: GO BO output_config={"effort": "medium"} (them 05/08) sau khi do tren du lieu that.
    # Effort thap khien model suy luan nong hon MOI luot nen phai di NHIEU VONG tool hon moi ra dap an,
    # cham tran MAX_TOOL_ROUNDS roi roi vao nhanh fallback "cau hoi qua phuc tap":
    #   - ty le nguoi dung nhan cau tu choi: 0,5% (2/384, 20/07-04/08) -> 27,0% (10/37, 06/08)
    #   - ty le cham tran 4 vong: 8,2% -> 37,1%; phan bo so lenh goi don dong dung tai moc 4
    # KHONG phai do MAX_TOOL_ROUNDS=4: ngay 04/08 tran da la 4 ma ty le tu choi van 0%.
    # Doi lai, effort chi tiet kiem ~0,005 USD/cau (output 1.473 -> 990 token) trong khi breakpoint
    # cache o duoi tiet kiem ~0,025 USD/cau (input 14.734 -> 1.791) - bo effort chi mat ~10% khoan
    # tiet kiem nhung lay lai 27% so cau tra loi duoc. Cac toi uu khac GIU NGUYEN.
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_blocks,
            tools=tools_for_request,
            messages=messages,
            extra_headers=_CACHE_BETA_HEADERS,
        )
        compute_and_log_cost(resp.usage, MODEL, question, session_id, username)
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            answer_text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not answer_text:
                # Truong hop hy huu: het ngan sach token cho phan suy luan (thinking) khien khong con
                # cho phan text tra ve - thu lai 1 lan voi yeu cau tra loi ngay, ngan gon.
                # 05/08/2026: nguyen nhan goc la Sonnet 5 bat thinking MAC DINH khi khong truyen
                # output_config - thinking an het MAX_TOKENS truoc khi con cho text tra loi.
                # 06/08/2026: da GO effort="medium" o ca 2 lenh goi (xem ghi chu dai o vong lap tren) -
                # co che thu lai nay GIU NGUYEN vi no van la luoi an toan cho dung tinh huong tren.
                messages.append({"role": "user", "content": "Hay tra loi ngay bay gio, ngan gon truc tiep."})
                resp2 = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=system_blocks,
                                                tools=tools_for_request, messages=messages,
                                                extra_headers=_CACHE_BETA_HEADERS)
                compute_and_log_cost(resp2.usage, MODEL, question, session_id, username)
                answer_text = "".join(b.text for b in resp2.content if b.type == "text").strip()
                if not answer_text:
                    answer_text = ("Xin lỗi, dữ liệu trả về quá lớn để tổng hợp gọn trong 1 câu trả lời. "
                                    "Bạn thử hỏi cụ thể/thu hẹp phạm vi hơn giúp mình nhé (vd theo vùng, theo thời gian ngắn hơn).")
            append_message(session_id, "user", question)
            append_message(session_id, "assistant", answer_text)
            if last_tool_used:
                set_query_state(session_id, last_tool_used[0], last_tool_used[1])
            if ran_adhoc_query:
                save_example(*ran_adhoc_query)
            return {"answer": answer_text, "sql_used": sql_used, "last_result": last_result}

        tool_results = []
        original_tool_uses = [b for b in resp.content if b.type == "tool_use"]
        # Gop cac lenh goi cung tool + cung tham so phu thanh mot (xem _merge_bulk_tool_calls - da tach
        # ra ngoai de test duoc, va da va 2 loi gay mat du lieu am tham vao 10/08/2026).
        merged_sub_ids = _merge_bulk_tool_calls(original_tool_uses)

        executed_count = 0
        for tu in original_tool_uses:
            if tu.id in merged_sub_ids:
                # Merged into primary tool_use -> return matching dummy tool_result to satisfy Anthropic API contract
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({"note": "Đã gộp kết quả tra cứu hàng loạt vào lượt gọi trước."}),
                })
                continue

            if executed_count >= MAX_TOOLS_PER_ROUND:
                # Capped execution -> return notice to satisfy Anthropic API contract
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({"note": f"Đã đạt giới hạn {MAX_TOOLS_PER_ROUND} lượt gọi tool trong 1 lượt. Hãy tổng hợp từ dữ liệu đã lấy, hoặc gọi các tool còn lại ở lượt kế tiếp."}),
                })
                continue

            executed_count += 1
            if tu.name in LOCAL_UTIL_TOOLS:
                # Tool "tien ich" chay bang code thuan, khong cham DB - xu ly ngay tai cho, khong qua
                # run_query/call_template (khong can audit log SQL vi khong co SQL nao ca).
                sql_used.append(f"[tien ich] {tu.name}({tu.input})")
                if tu.name == "get_current_datetime":
                    payload = get_current_datetime()
                elif tu.name == "resolve_relative_date":
                    payload = resolve_relative_date(tu.input.get("phrase", ""))
                elif tu.name == "save_business_term":
                    save_glossary_term(tu.input.get("term", ""), tu.input.get("definition", ""),
                                        defined_by=username)
                    payload = {"ok": True, "message": "Da luu dinh nghia."}
                else:
                    payload = {"error": f"Tool khong ro: {tu.name}"}
            elif tu.name in RAW_SQL_TOOLS:
                if scope_area_code or scope_channel:
                    # Phong ho: tool nay khong con trong tools_for_request nen AI khong the goi duoc,
                    # nhung neu vi ly do gi van xuat hien thi tu choi thang, KHONG thuc thi SQL.
                    sql_used.append(f"[BI CHAN - tai khoan gioi han] {tu.name}")
                    payload = {"error": "Tai khoan cua ban bi gioi han (vung/kenh), khong duoc dung truy van SQL tu do."}
                else:
                    db = RAW_SQL_TOOLS[tu.name]
                    sql = tu.input.get("sql", "")
                    sql_used.append(f"[{db}] {sql}")
                    result = run_query(sql, question=question, db=db, username=username, session_id=session_id)
                    last_result = result
                    last_tool_used = (tu.name, str(tu.input))
                    if db == "local" and result["ok"]:
                        ran_adhoc_query = (question, sql)
                    payload = ({"columns": result["columns"], "rows": result["rows"][:MAX_ROWS_TO_MODEL],
                                "row_count": result["row_count"]} if result["ok"] else {"error": result["error"]})
            else:
                sql_used.append(f"[bao cao chuan] {tu.name}({tu.input})")
                tresult = call_template(tu.name, tu.input, question=question, username=username, session_id=session_id,
                                         scope_area_code=scope_area_code, scope_employee_code=scope_employee_code,
                                         scope_channel=scope_channel, scope_role=scope_role)
                last_result = tresult
                last_tool_used = (tu.name, str(tu.input))
                payload = tresult["result"] if tresult["ok"] else {"error": tresult["error"]}
                # 22/07/2026 (diem #5): tool co the kem canh bao tu-doi-chieu (vd tong theo vung lech
                # tong tho). TRUOC DAY chi lay ["result"] nen canh bao BI ROI MAT truoc khi toi model
                # -> nguoi dung van nhan so lieu sai ma khong he biet. Chi boc them khi CO canh bao.
                if tresult.get("canh_bao"):
                    payload = {"du_lieu": payload,
                               "CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG": tresult["canh_bao"]}

            # Gioi han kich thuoc payload gui cho AI de tranh context phinh to khi goi nhieu tool
            # lien tiep (truoc day template tools tra JSON 20K-50K chars, cong don qua cac vong lam
            # input tang tu 7K len 49K tokens cho 1 cau hoi). last_result (dong 804) VAN giu nguyen
            # ket qua day du cho UI frontend - chi phan gui cho AI model bi cat.
            payload_str = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload)
            if len(payload_str) > MAX_PAYLOAD_CHARS:
                payload_str = payload_str[:MAX_PAYLOAD_CHARS] + "\n...(du lieu bi cat bot vi qua dai, phan tren DA DU de tra loi - KHONG can query lai)"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": payload_str,
            })

        if tool_results:
            if _last_msg_cache_block is not None:
                _last_msg_cache_block.pop("cache_control", None)
            tool_results[-1] = dict(tool_results[-1])
            # 06/08/2026: TTL MAC DINH (5 phut), CO Y khac 2 breakpoint kia (system + tools dung "1h").
            # Gia GHI cache phu thuoc TTL: 5 phut = 1,25x gia input ($2,50/M), 1 gio = 2x ($4,00/M).
            # Khoi tool_result nay chi duoc doc lai TRONG CHINH cau hoi do - cac vong cach nhau vai
            # giay - nen khong bao gio huong loi tu TTL 1 gio, ma van phai tra gia ghi dat hon 60%.
            # Do that 06/08: cache_write la thanh phan DAT NHAT (37,8% chi phi/cau, ~4.426 token),
            # phan lon den tu chinh breakpoint di dong nay (ghi lai moi vong, ~2,86 vong/cau).
            # Ha ve 5 phut tiet kiem ~0,0066 USD/cau (~14% tong chi phi).
            # System prompt + tool definitions thi NGUOC LAI: dung lai qua nhieu cau hoi trong nhieu
            # gio, nen giu "1h" (xem system_blocks va tools_for_request o dau ham).
            # Rui ro: cache 5 phut chi hong neu 2 vong goi tool cach nhau qua 5 phut - do thuc te cau
            # cham nhat la 1,3 phut cho CA cau hoi, con xa nguong.
            tool_results[-1]["cache_control"] = {"type": "ephemeral"}
            _last_msg_cache_block = tool_results[-1]
        messages.append({"role": "user", "content": tool_results})

    fallback = "Xin loi, cau hoi qua phuc tap can nhieu buoc truy van, vui long hoi cu the hon."
    append_message(session_id, "user", question)
    append_message(session_id, "assistant", fallback)
    return {"answer": fallback, "sql_used": sql_used, "last_result": last_result}


def ask_stream(question: str, session_id: str = "default", username: str = None, scope_area_code: str = None,
                scope_employee_code: str = None, scope_channel: str = None, scope_role: str = None):
    """11/08/2026: BAN STREAMING cua ask() - GIONG HET logic tool-calling/phan quyen/cache o tren,
    CHI KHAC cach lay CAU TRA LOI CUOI CUNG: thay vi client.messages.create() cho xong het roi tra 1
    cuc JSON, dung client.messages.stream() de yield TUNG DOAN TEXT ngay khi model sinh ra - giup
    nguoi dung THAY chu xuat hien dan (giam cam giac "lag") thay vi man hinh trang cho toi khi xong.

    QUAN TRONG: CHI vong CUOI CUNG (khi model KHONG con goi tool nua, dang sinh cau tra loi that) moi
    stream - CAC VONG GIUA (goi tool: resolve_relative_date, get_revenue_by_channel...) VAN cho xong
    binh thuong nhu ask() vi nguoi dung khong can thay qua trinh AI goi tool, chi can thay cau tra
    loi cuoi cung xuat hien dan. Day la ham GENERATOR (dung yield) - goi ham nay tra ve 1 generator,
    PHAI duyet qua (for chunk in ask_stream(...)) moi thuc su chay.

    Ham nay la BAN SONG SONG voi ask() (KHONG sua ask() de tranh anh huong endpoint /chat dang chay
    that cho 25 users) - dung cho endpoint /chat/stream moi. Neu can sua logic tool-calling/phan quyen
    (vd them tool moi, sua cach EP scope), PHAI sua CA HAI ham nay (ask() va ask_stream()) - de tranh
    2 ham lech nhau dan, cac phan GIONG HET giua 2 ham duoc chua thich "xem ask()" thay vi lap lai
    toan bo comment giai thich.
    11/08/2026: RIENG phan GOP TOOL HANG LOAT (Tool Merger) da rut ra ham dung chung
    _merge_bulk_tool_calls() thay vi chep tay - phat hien luc nay ban chep tay o duoi van con giu 2
    loi da vas o ask() 1 ngay truoc (danh dau "da gop" gia, chi gop 1 tham so khoa lam vut het tham
    so khac). Phan nay KHONG can sua 2 noi nua, chi can sua trong _merge_bulk_tool_calls().

    yield: cac dict {"type": "text_delta", "text": str} cho tung doan chu, roi 1 dict cuoi cung
    {"type": "done", "answer": str, "sql_used": [...], "last_result": {...}} voi KET QUA DAY DU
    (giong het cau truc return cua ask()) de client biet ket thuc va co du lieu cho UI (bang/cot...).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key == "mock-key-for-local-testing":
        msg = ("⚠️ **Chưa cấu hình API Key Claude/Anthropic**: Vui lòng bổ sung biến "
               "`ANTHROPIC_API_KEY=sk-ant-api03...` vào file `backend/.env` để khởi chạy tính năng "
               "Phân tích Dữ liệu AI.")
        yield {"type": "text_delta", "text": msg}
        yield {"type": "done", "answer": msg, "sql_used": [], "last_result": None}
        return

    client = anthropic.Anthropic(api_key=api_key)
    history = load_history(session_id, max_turns=MAX_HISTORY_TURNS)
    messages = list(history) + [{"role": "user", "content": question}]
    _last_msg_cache_block = None  # xem ghi chu day du o ask()

    sql_used = []
    last_result = None
    last_tool_used = None
    ran_adhoc_query = None

    tools_for_request = ALL_TOOLS_CACHED
    if scope_area_code or scope_channel:
        scoped_tools = [t for t in ALL_TOOLS if t["name"] not in RAW_SQL_TOOLS]
        tools_for_request = scoped_tools[:-1] + [{**scoped_tools[-1], "cache_control": {"type": "ephemeral", "ttl": "1h"}}]

    system_blocks = [
        {"type": "text", "text": _static_system_prompt(), "cache_control": {"type": "ephemeral", "ttl": "1h"}},
        {"type": "text", "text": _dynamic_context_note(question, session_id, scope_area_code, scope_employee_code, scope_channel)},
    ]

    for round_i in range(MAX_TOOL_ROUNDS):
        is_last_possible_round = round_i == MAX_TOOL_ROUNDS - 1
        # Vong GIUA: co the con tool_use, KHONG stream (client khong can thay) - dung create() nhu
        # ask() binh thuong, ro rang hon la stream() roi bo qua cac delta.
        # Vong CO THE la CUOI (round_i == MAX_TOOL_ROUNDS-1): CHUA BIET truoc model co con goi tool
        # hay khong (chi biet SAU khi nhan xong response) - nhung neu dung create() cho vong nay, khi
        # model THAT SU tra loi (khong goi tool) thi lai mat streaming cho chinh vong quan trong nhat.
        # Giai phap: LUON dung stream() tu vong DAU (khong chi vong cuoi) - phi stream cho vong co
        # tool_use la KHONG DANG KE (chi vai token dau ra truoc phan tool_use, van phai doi ca cuc
        # tool_use ve moi biet dc functon nao/tham so gi de goi that), doi lai dam bao vong tra loi
        # that SU (bat ky la vong thu may) LUON duoc stream.
        with client.messages.stream(
            model=MODEL, max_tokens=MAX_TOKENS, system=system_blocks,
            tools=tools_for_request, messages=messages, extra_headers=_CACHE_BETA_HEADERS,
        ) as stream:
            has_tool_use_so_far = False
            for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "tool_use":
                    has_tool_use_so_far = True
                elif event.type == "text" and not has_tool_use_so_far:
                    # event.type=="text" la text delta da ghep san (tien ich cua SDK) - CHI yield khi
                    # CHUA thay tool_use nao trong response nay (tranh lo doan text "suy nghi truoc
                    # khi goi tool" hiem gap ra nguoi dung, gay hieu lam la cau tra loi that).
                    yield {"type": "text_delta", "text": event.text}
            resp = stream.get_final_message()

        compute_and_log_cost(resp.usage, MODEL, question, session_id, username)
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            answer_text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not answer_text:
                # Xem ghi chu day du o ask() - truong hop hy huu het ngan sach thinking.
                messages.append({"role": "user", "content": "Hay tra loi ngay bay gio, ngan gon truc tiep."})
                with client.messages.stream(model=MODEL, max_tokens=MAX_TOKENS, system=system_blocks,
                                             tools=tools_for_request, messages=messages,
                                             extra_headers=_CACHE_BETA_HEADERS) as stream2:
                    for event in stream2:
                        if event.type == "text":
                            yield {"type": "text_delta", "text": event.text}
                    resp2 = stream2.get_final_message()
                compute_and_log_cost(resp2.usage, MODEL, question, session_id, username)
                answer_text = "".join(b.text for b in resp2.content if b.type == "text").strip()
                if not answer_text:
                    answer_text = ("Xin lỗi, dữ liệu trả về quá lớn để tổng hợp gọn trong 1 câu trả lời. "
                                    "Bạn thử hỏi cụ thể/thu hẹp phạm vi hơn giúp mình nhé (vd theo vùng, theo thời gian ngắn hơn).")
                    yield {"type": "text_delta", "text": answer_text}
            append_message(session_id, "user", question)
            append_message(session_id, "assistant", answer_text)
            if last_tool_used:
                set_query_state(session_id, last_tool_used[0], last_tool_used[1])
            if ran_adhoc_query:
                save_example(*ran_adhoc_query)
            yield {"type": "done", "answer": answer_text, "sql_used": sql_used, "last_result": last_result}
            return

        # Tu day tro xuong: XU LY TOOL. Truoc 11/08/2026 cho nay COPY TAY logic gop tool tu ask() -
        # dung cach do gia mao chinh 2 loi da vas o ask() ngay 10/08 (danh dau "da gop" ke ca khong
        # gop duoc gi; chi gop 1 tham so khoa, am tham vut tham so khac - xem _merge_bulk_tool_calls
        # o tren). Doi sang GOI CHUNG ham do thay vi giu 2 ban chep tay de khong bao gio lech nhau
        # nua (dung y tinh than ghi chu cu: "PHAI sua o day theo dung y het").
        tool_results = []
        original_tool_uses = [b for b in resp.content if b.type == "tool_use"]
        merged_sub_ids = _merge_bulk_tool_calls(original_tool_uses)

        executed_count = 0
        for tu in original_tool_uses:
            if tu.id in merged_sub_ids:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({"note": "Đã gộp kết quả tra cứu hàng loạt vào lượt gọi trước."}),
                })
                continue

            if executed_count >= MAX_TOOLS_PER_ROUND:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({"note": f"Đã đạt giới hạn {MAX_TOOLS_PER_ROUND} lượt gọi tool trong 1 lượt. Hãy tổng hợp từ dữ liệu đã lấy, hoặc gọi các tool còn lại ở lượt kế tiếp."}),
                })
                continue

            executed_count += 1
            if tu.name in LOCAL_UTIL_TOOLS:
                sql_used.append(f"[tien ich] {tu.name}({tu.input})")
                if tu.name == "get_current_datetime":
                    payload = get_current_datetime()
                elif tu.name == "resolve_relative_date":
                    payload = resolve_relative_date(tu.input.get("phrase", ""))
                elif tu.name == "save_business_term":
                    save_glossary_term(tu.input.get("term", ""), tu.input.get("definition", ""),
                                        defined_by=username)
                    payload = {"ok": True, "message": "Da luu dinh nghia."}
                else:
                    payload = {"error": f"Tool khong ro: {tu.name}"}
            elif tu.name in RAW_SQL_TOOLS:
                if scope_area_code or scope_channel:
                    sql_used.append(f"[BI CHAN - tai khoan gioi han] {tu.name}")
                    payload = {"error": "Tai khoan cua ban bi gioi han (vung/kenh), khong duoc dung truy van SQL tu do."}
                else:
                    db = RAW_SQL_TOOLS[tu.name]
                    sql = tu.input.get("sql", "")
                    sql_used.append(f"[{db}] {sql}")
                    result = run_query(sql, question=question, db=db, username=username, session_id=session_id)
                    last_result = result
                    last_tool_used = (tu.name, str(tu.input))
                    if db == "local" and result["ok"]:
                        ran_adhoc_query = (question, sql)
                    payload = ({"columns": result["columns"], "rows": result["rows"][:MAX_ROWS_TO_MODEL],
                                "row_count": result["row_count"]} if result["ok"] else {"error": result["error"]})
            else:
                sql_used.append(f"[bao cao chuan] {tu.name}({tu.input})")
                tresult = call_template(tu.name, tu.input, question=question, username=username, session_id=session_id,
                                         scope_area_code=scope_area_code, scope_employee_code=scope_employee_code,
                                         scope_channel=scope_channel, scope_role=scope_role)
                last_result = tresult
                last_tool_used = (tu.name, str(tu.input))
                payload = tresult["result"] if tresult["ok"] else {"error": tresult["error"]}
                if tresult.get("canh_bao"):
                    payload = {"du_lieu": payload,
                               "CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG": tresult["canh_bao"]}

            payload_str = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload)
            if len(payload_str) > MAX_PAYLOAD_CHARS:
                payload_str = payload_str[:MAX_PAYLOAD_CHARS] + "\n...(du lieu bi cat bot vi qua dai, phan tren DA DU de tra loi - KHONG can query lai)"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": payload_str,
            })

        if tool_results:
            if _last_msg_cache_block is not None:
                _last_msg_cache_block.pop("cache_control", None)
            tool_results[-1] = dict(tool_results[-1])
            tool_results[-1]["cache_control"] = {"type": "ephemeral"}
            _last_msg_cache_block = tool_results[-1]
        messages.append({"role": "user", "content": tool_results})

    fallback = "Xin loi, cau hoi qua phuc tap can nhieu buoc truy van, vui long hoi cu the hon."
    append_message(session_id, "user", question)
    append_message(session_id, "assistant", fallback)
    yield {"type": "text_delta", "text": fallback}
    yield {"type": "done", "answer": fallback, "sql_used": sql_used, "last_result": last_result}
