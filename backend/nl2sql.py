# -*- coding: utf-8 -*-
"""NL2SQL: dung Claude (tool use) de hieu cau hoi tieng Viet, tra loi tu nhien.

Kien truc HYBRID de tang do chinh xac cho cac bao cao hay dung:
  - Cau hoi thuoc nhom bao cao CHUAN (doanh thu theo kenh, top san pham, top khach hang,
    vung mien, KPI nhan vien, so sanh 2 khoang thoi gian) -> goi truc tiep cac ham da kiem chung
    trong report_templates.py, AI KHONG tu sinh SQL cho nhom nay.
  - Cau hoi AD-HOC ngoai cac mau tren -> fallback ve query_database (local SQLite); neu warehouse
    chua phu object/cot thi tim catalog dong va query SQL Server live bang tai khoan read-only.

Bao cao chuan van doc kho "local" de nhanh/on dinh. SQL Server live chi la fallback cho tai khoan
duoc phep va du lieu chua dong bo; moi query bi validate chi-doc, gioi han dong, timeout va audit.

Ho tro NHO NGU CANH da luot (conversation_memory.py) - moi session (1 phien chat webapp) duoc
nho lai vai cau hoi/tra loi gan nhat, de cau hoi tiep theo khong can nhac lai tu dau.
"""
import os
import json
from collections import defaultdict
import anthropic
from schema_context import SCHEMA_CONTEXT
from query_engine import run_query
from report_templates import call_template, latest_data_date
from conversation_memory import load_history, append_message, get_query_state, set_query_state
from data_freshness import FreshnessCollector
from realtime_context import REALTIME_TOOLS, REALTIME_TOOL_NAMES, get_current_datetime, resolve_relative_date
from glossary_memory import save_glossary_term, retrieve_relevant_glossary
from longterm_memory import save_example, retrieve_similar_examples
from cost_logger import compute_and_log_cost
from feature_policy import (
    DISABLED_FUTURE_TOOL_NAMES,
    FUTURE_FORECAST_DISABLED_MESSAGE,
    is_future_forecast_question,
)
from sql_schema_retriever import relevant_schema_context, search_sql_catalog

# 13/08/2026: cho phep tro sang nha cung cap khac de THU NGHIEM, mac dinh KHONG doi gi.
# DeepSeek V4 co endpoint dinh dang Anthropic (https://api.deepseek.com/anthropic) nen dung duoc
# nguyen SDK anthropic va nguyen dinh dang tool_use/tool_result - khong phai viet lai vong goi tool.
# Bat bang bien moi truong, vi du trong backend/.env:
#     LLM_BASE_URL=https://api.deepseek.com/anthropic
#     LLM_MODEL=deepseek-v4-pro
#     LLM_API_KEY=sk-...
# Bo trong ca 3 -> chay Claude y het truoc day.
MODEL = os.environ.get("LLM_MODEL", "").strip() or "claude-sonnet-5"
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "").strip()

# Cac tinh nang CHI Anthropic co. Tro sang nha cung cap khac thi phai tat, neu khong API se tu choi
# hoac lang le bo qua - ca hai deu kho phat hien.
IS_ANTHROPIC = not LLM_BASE_URL or "anthropic.com" in LLM_BASE_URL
MAX_TOOL_ROUNDS = 6  # 17/08/2026: chot 6 - muc dung giua sau khi con so nay bi keo qua lai 3 lan.
                     # Lich su, giu lai ca hai phia de nguoi sau khong lap lai tranh luan:
                     #   8  (ban dau)  - cau hoi dieu hanh co the can nhieu buoc that; moi intent pho
                     #                   bien da duoc gom vao composite tool nen 8 chi la luoi an toan
                     #                   cho ad-hoc, khong phai muc tieu.
                     #   4  (04/08)    - do duoc: ha 8->4 rut ngan 5-8 giay moi cau tra loi. 10/08 giu
                     #                   nguyen 4 vi CA 2 ca "cau hoi qua phuc tap" truy duoc nguyen
                     #                   nhan deu do MO TA TOOL chua ro khien model goi lap, sua cau
                     #                   chu la het - KHONG phai do thieu vong.
                     #   8  (c9883d5)  - nang lai khi them cac bao cao nhieu buoc da kiem chung.
                     # 6 la muc nguoi dung chot: du cho bao cao nhieu buoc, van cat bot phan duoi cua
                     # 8 vong von chi cham vao khi model di lac. Neu lai thay "cau hoi qua phuc tap",
                     # kiem MO TA TOOL truoc khi nghi den viec nang so nay - tien le 10/08 cho thay
                     # nguyen nhan nam o cau chu, khong nam o so vong.
MAX_TOOLS_PER_ROUND = 5  # 10/08/2026: truoc day so 3 nam hardcode giua ham ask(). Nang 3 -> 5 vi sau
                          # khi va loi Tool Merger (xem _merge_bulk_tool_calls), cac lenh goi KHAC
                          # tham so nay chay THAT thay vi bi bo am tham, nen can them cho.
MAX_UNIQUE_TOOL_CALLS = 12  # Chan chi phi: cung tool+cung tham so chi chay 1 lan trong mot cau hoi.
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
        "name": "get_customer_revenue_debt_risk",
        "description": "Tim trong DUNG 1 LAN cac khach hang dong thoi co doanh thu lon, no qua han "
                       "cao va doanh thu dang giam so voi giai doan truoc. BAT BUOC dung cho cau hoi "
                       "'khach hang doanh thu lon, cong no cao, xu huong mua giam' va cac cach hoi "
                       "tuong duong. Tool tu so sanh hai giai doan cung do dai, noi doanh thu voi "
                       "snapshot cong no da chuan hoa va ep pham vi tai khoan. KHONG goi tach top "
                       "khach + cong no + so sanh ky thanh nhieu vong, KHONG viet SQL ad-hoc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "as_of_date": {"type": "string", "description": "YYYY-MM-DD; mac dinh ngay du lieu moi nhat."},
                "recent_months": {"type": "integer", "description": "So thang moi giai doan, mac dinh 3."},
                "min_revenue": {"type": "number", "description": "Doanh thu toi thieu ky gan nhat, mac dinh 100 trieu dong."},
                "min_overdue": {"type": "number", "description": "No qua han toi thieu, mac dinh 50 trieu dong."},
                "limit": {"type": "integer", "description": "So khach toi da, mac dinh 20."},
            },
            "required": [],
        },
    },
    {
        "name": "get_promotion_effectiveness",
        "description": "Danh gia HIEU QUA TUNG CHUONG TRINH KHUYEN MAI theo doanh thu gan voi don "
                       "hang co ap dung chuong trinh, so khach hang tham gia, so don va so san pham. "
                       "BAT BUOC dung tool nay cho cau hoi 'danh gia hieu qua CTKM/khuyen mai', 'CTKM "
                       "nao co doanh thu/khach hang cao', hoac cau hoi ket hop CTKM + doanh thu + khach "
                       "hang + san pham. GOI DUNG 1 LAN, KHONG search catalog va KHONG query/group theo "
                       "cot CTKM cua hoa don: cot do la GHI CHU TU DO, co the chua ten/so dien thoai va "
                       "da tung tao ket qua sai. Tool dung lien ket DMS_DonHangCTKM -> DMS_CTKM that, "
                       "tu kiem tra moc du lieu va mac dinh chon thang DAY DU gan nhat neu user khong "
                       "noi ky. associated_revenue la doanh thu gan voi don co CTKM, KHONG duoc cong "
                       "cac dong hoac goi la ROI/uplift vi mot don co the dung nhieu CTKM.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "YYYY-MM-DD; bo trong de tool tu chon thang day du gan nhat."},
                "date_to": {"type": "string", "description": "YYYY-MM-DD; bo trong de tool tu chon thang day du gan nhat."},
                "limit": {"type": "integer", "description": "So chuong trinh toi da, mac dinh 20, toi da 50."},
            },
            "required": [],
        },
    },
    {
        "name": "get_salary_bonus_policy",
        "description": "Tra QUY TAC/CACH TINH/BAC TIEN cua V15, V22, V25 hoac ASO tu DIM_BacThuong, "
                       "dong thoi doi chieu voi so thuong da chot trong FACT_ThongKeTinhLuong. BAT BUOC "
                       "dung tool nay khi hoi 'V25 duoc tinh nhu the nao', 'cac bac tien V15/V22/V25', "
                       "'cong thuc thuong ASO', 'vi sao dat ty le ma thuong bang 0', hoac cau hoi mo ho "
                       "kieu 'V25 cua tung ASO'. GOI DUNG 1 LAN; KHONG search catalog/query SQL thu cong. "
                       "Tool tu phan biet: ASO trong du lieu DNH la CHI TIEU/KHOAN THUONG khach hang "
                       "hoat dong, khong phai chuc danh. Tool con kiem tra chenh lech giua bang quy tac, "
                       "stored procedure va so V25Bonus da luu; neu co chenh lech PHAI noi ro, KHONG tu "
                       "tinh de/ghi de so da chot cua SQL Server.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bonus_type": {"type": "string", "enum": ["v15", "v22", "v25", "aso"], "description": "Loai thuong can giai thich."},
                "as_of_date": {"type": "string", "description": "YYYY-MM hoac YYYY-MM-DD; mac dinh ky luong day du gan nhat."},
                "area_code": {"type": "string", "description": "Loc MB/MT/MN neu nguoi dung neu ro."},
                "position_code": {"type": "string", "description": "Loc TDV/QLV/TP/PP/TBP/CS/TK/CTV neu nguoi dung neu ro."},
            },
            "required": ["bonus_type"],
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

QUERY_SQL_SERVER_TOOL = {
    "name": "query_sql_server",
    "description": (
        "FALLBACK CHI-DOC tren SQL Server Bravo LIVE cho du lieu/business object chua duoc dong bo vao "
        "warehouse.db va khong co tool bao cao chuan. CHI dung sau khi da xem schema lien quan trong "
        "context hoac goi search_sql_server_catalog. Dung T-SQL: TOP N, dbo.[TenObject], KHONG LIMIT, "
        "KHONG SELECT *. Chi SELECT/WITH; cam EXEC stored procedure, ghi/sua/xoa, SELECT INTO va truy van "
        "sang database khac. Du lieu live la nguon chinh de kiem tra do phu, nhung voi doanh thu/cong no/"
        "KPI da co tool chuan thi van BAT BUOC dung tool chuan truoc. Tool live chi kha dung cho vai tro "
        "C-Level/Admin do SQL tu do khong the ep phan quyen dong theo moi bang."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "Mot cau SELECT/WITH T-SQL chi-doc, nen co TOP N."},
            "explanation": {"type": "string", "description": "Muc dich nghiep vu va object duoc dung."},
        },
        "required": ["sql"],
    },
}

SEARCH_SQL_CATALOG_TOOL = {
    "name": "search_sql_server_catalog",
    "description": (
        "Tim table/view/stored procedure va cot lien quan trong TOAN BO catalog SQL Server duoc cap quyen. "
        "Dung khi cau hoi nhac toi du lieu chua co trong schema warehouse viet san, khi chua chac ten object/"
        "cot, hoac can doc logic definition cua view/stored procedure. Tool chi doc metadata, khong doc dong "
        "du lieu va khong EXEC procedure. Sau khi tim thay table/view, dung query_sql_server neu tai khoan co quyen."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Tu khoa nghiep vu hoac ten object/cot can tim."},
            "limit": {"type": "integer", "description": "So object toi da, mac dinh 6, toi da 12."},
            "include_definition": {"type": "boolean", "description": "Co lay definition view/SP neu quyen cho phep."},
        },
        "required": ["query"],
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

RAW_SQL_TOOLS = {
    "query_database": "local",
    "query_inventory_receivables": "supabase",
    "query_sql_server": "bravo",
}
LIVE_SQL_TOOL_NAMES = {"query_sql_server"}
LIVE_SQL_ALLOWED_ROLES = {"c_level", "admin_ops"}
LOCAL_UTIL_TOOLS = REALTIME_TOOL_NAMES | {"save_business_term", "search_sql_server_catalog"}

# Chinh sach 14/08/2026: loc o tang code, khong chi dua vao prompt. Ke ca khi mot
# tool du bao cu con sot lai trong danh sach khai bao phia tren, no cung khong bao
# gio duoc gui cho model.
TEMPLATE_TOOLS = [
    tool for tool in TEMPLATE_TOOLS if tool["name"] not in DISABLED_FUTURE_TOOL_NAMES
]
ALL_TOOLS = (
    TEMPLATE_TOOLS
    + [QUERY_TOOL, QUERY_SUPABASE_TOOL, QUERY_SQL_SERVER_TOOL, SEARCH_SQL_CATALOG_TOOL]
    + REALTIME_TOOLS
    + [SAVE_GLOSSARY_TOOL]
)
# Tools KHONG bao gio doi trong 1 phien chay - danh cache_control tren tool CUOI CUNG de cache ca
# mang tools (Anthropic cache theo kieu "prefix": danh dau 1 block = cache moi thu TINH DEN block do).
ALL_TOOLS_CACHED = ALL_TOOLS[:-1] + [{**ALL_TOOLS[-1], "cache_control": {"type": "ephemeral", "ttl": "1h"}}]


def _cache_tools(tools: list[dict]) -> list[dict]:
    if not tools:
        return []
    return tools[:-1] + [{**tools[-1], "cache_control": {"type": "ephemeral", "ttl": "1h"}}]


def _tools_for_request(scope_area_code: str = None, scope_channel: str = None,
                       scope_role: str = None) -> list[dict]:
    """Phan quyen tool o tang code, dung chung cho ask va ask_stream."""
    tools = ALL_TOOLS
    if scope_area_code or scope_channel:
        tools = [tool for tool in tools if tool["name"] not in RAW_SQL_TOOLS]
    elif scope_role not in LIVE_SQL_ALLOWED_ROLES:
        tools = [tool for tool in tools if tool["name"] not in LIVE_SQL_TOOL_NAMES]
    return ALL_TOOLS_CACHED if tools is ALL_TOOLS else _cache_tools(tools)


_SCHEMA_COVERAGE_ERROR_MARKERS = (
    "no such table",
    "no such column",
    "has no column named",
    "invalid object name",
    "invalid column name",
)


def _raw_query_payload(result: dict, db: str, question: str) -> dict:
    if result.get("ok"):
        return {
            "columns": result["columns"],
            "rows": result["rows"][:MAX_ROWS_TO_MODEL],
            "row_count": result["row_count"],
            "truncated": result.get("truncated", False),
            "database": result.get("database", db),
        }

    payload = {"error": result.get("error", "Loi truy van khong xac dinh")}
    error_lower = payload["error"].lower()
    if db == "local" and any(marker in error_lower for marker in _SCHEMA_COVERAGE_ERROR_MARKERS):
        try:
            payload["sql_server_catalog_fallback"] = search_sql_catalog(
                question, limit=8, include_definition=False
            )
            payload["next_action"] = (
                "Warehouse khong phu schema nay. Dung object/cot trong catalog fallback de tao T-SQL "
                "va goi query_sql_server neu tool kha dung; khong ket luan la khong truy cap duoc du lieu."
            )
        except Exception as exc:
            payload["catalog_error"] = str(exc)[:180]
    return payload

# Beta header can thiet de dung TTL 1h (mac dinh cache_control chi song 5 phut neu khong co header nay).
# Ap dung cho toan bo request (system + tools) - giup cache song qua nhieu cau hoi lien tiep trong gio
# hanh chinh thay vi het han sau vai phut, tang ty le cache-hit (chi ~10% gia input goc khi hit).
_CACHE_BETA_HEADERS = ({"anthropic-beta": "extended-cache-ttl-2025-04-11"} if IS_ANTHROPIC else {})


def _llm_client():
    """Client goi model. Doc key theo thu tu LLM_API_KEY -> ANTHROPIC_API_KEY de doi nha cung cap
    ma khong phai xoa key cu (doi lai chi can bo LLM_* la ve Claude ngay)."""
    from llm_provider import resolve_api_key
    key = resolve_api_key()   # thu tu uu tien dinh nghia MOT cho, xem llm_provider.py
    # CHI truyen base_url khi thuc su doi nha cung cap. Truyen base_url=None cung la them mot doi so,
    # va cac test dang gia lap anthropic.Anthropic bang lambda chi nhan api_key se vo ngay
    # (da dinh: test_repeated_tool_call_is_not_reexecuted_and_forces_final_answer). Giu duong mac dinh
    # goi y het truoc day thi khong the lam hong thu gi dang chay.
    if LLM_BASE_URL:
        return anthropic.Anthropic(api_key=key, base_url=LLM_BASE_URL)
    return anthropic.Anthropic(api_key=key)


def _static_system_prompt() -> str:
    """Phan TINH cua system prompt (quy tac + schema) - KHONG bao gio doi giua cac lan goi, nen danh
    cache_control (TTL 1h) o day. Moc ngay du lieu ("hom nay") la phan DONG, tach rieng o
    _dynamic_context_note() de khong lam vo cache moi 15-30 phut khi kho dong bo lai."""
    return f"""Ban la AI Analyst chuyen phan tich du lieu kinh doanh cho Duoc Nam Ha (DNH),
mot doanh nghiep duoc pham. Nguoi dung se hoi bang tieng Viet ve doanh thu, cong no, KPI nhan vien,
ton kho, vung mien... Ban dung cac tool duoc cung cap de truy van du lieu THAT. Bao cao chuan uu tien
warehouse.db da doi chieu; du lieu chua duoc warehouse phu thi tim trong catalog va doc SQL Server
live neu tai khoan duoc phep. Tra loi dua tren ket qua da truy van - KHONG duoc bia so lieu.

Neu cuoc hoi thoai co cac luot truoc do, HAY DUNG NGU CANH DO de hieu cau hoi hien tai (vd neu vua
hoi "doanh thu thang 6" roi hoi tiep "con thang 5?", hieu la van hoi doanh thu theo kenh/tieu chi
tuong tu nhung doi sang thang 5) - KHONG hoi lai nguoi dung nhung gi da ro tu ngu canh truoc.

QUAN TRONG VE CHON TOOL:
- ⚠️  KHONG BAO GIO nhac ten tool/ham/truong ky thuat trong cau tra loi cho nguoi dung. Nguoi doc la
  lanh dao kinh doanh, khong phai lap trinh vien. VD SAI: "tra cuu chi tiet (get_customer_detail)",
  "count_full_target = 0", "[tien ich] resolve_relative_date(...)". VD DUNG: "toi co the tra cuu chi
  tiet tung khach hang de xem ai phu trach". Mo ta viec lam bang ngon ngu nghiep vu, giau het ten ky
  thuat ben trong.
- Neu cau hoi thuoc cac nhom bao cao chuan: doanh thu theo kenh, top san pham, top khach hang, doanh thu
  theo vung mien, KPI/doanh so nhan vien (tong quan/thang), KPI THEO NGAY 1 nhan vien ca nhan, SO SANH
  2 khoang thoi gian, CHI TIET 1 khach hang cu the, TRA CUU ma/ten/vai tro nhan vien, KIEM TRA don hang
  bat thuong/chay don KPI, TON KHO THEO VUNG, LICH SU DOI QLV, CAY DOANH THU/KPI TP-QLV-TDV, XEP HANG
  KPI, DOI CHIEU doanh thu tu tren xuong vs cong don tu duoi len, LICH SU TRUY VAN/CHI PHI AI cua chinh
  nguoi dang hoi, HIEU QUA CHUONG TRINH KHUYEN MAI, QUY TAC/BAC TIEN V15-V22-V25-ASO,
  THUONG KINH DOANH/PHU CAP thang cua 1 nhan vien -> BAT BUOC dung tool tuong ung
  (get_revenue_by_channel, get_top_products, get_top_customers, get_revenue_by_region, get_employee_kpi,
  get_employee_daily_kpi, compare_periods, get_customer_detail, get_employee_directory, check_order_timing,
  get_inventory_by_region, get_qlv_change_history, get_revenue_tree, get_kpi_ranking,
  get_revenue_reconciliation, get_receivables_overview, get_customer_revenue_debt_risk,
  get_audit_log, get_promotion_effectiveness,
  get_salary_bonus_policy, get_salary_detail, get_salary_achievement_summary).
- HIEU QUA CTKM: BAT BUOC goi get_promotion_effectiveness DUNG 1 LAN. KHONG duoc GROUP BY cot CTKM
  tren vHoaDon/vHoaDonTotal: cot do la ghi chu tu do, co the chua ten nguoi va so dien thoai. Doanh
  thu chuong trinh phai noi qua DMS_DonHangCTKM -> DMS_CTKM. Neu tool bao nguon lien ket chi den mot
  moc cu, noi ro moc do; KHONG lay ghi chu hoa don thay the va KHONG suy dien phan thieu.
- CACH TINH/BAC TIEN V15/V22/V25/ASO: BAT BUOC goi get_salary_bonus_policy DUNG 1 LAN. Neu tool phat
  hien bang quy tac, stored procedure va so da chot khong khop, PHAI neu ro chenh lech va van phan
  biet 'so SQL Server da chot' voi 'so theo bang quy tac'; KHONG tu sua so thay ke toan/DNH.
- Cau hoi ket hop KHACH DOANH THU LON + CONG NO CAO + XU HUONG MUA GIAM: goi
  get_customer_revenue_debt_risk DUNG 1 LAN. Tool da noi hai ky doanh thu voi snapshot cong no;
  KHONG tach thanh nhieu tool/query lap lai.
- DU BAO TUONG LAI DA TAT: TUYET DOI KHONG du bao, du phong, uoc tinh, ngoai suy hoac tu tinh mot
  gia tri tuong lai cho doanh thu, doanh so, KPI, cong no, ton kho, khach hang hay "kha nang dat".
  Khong duoc dung SQL tu do de lach quy tac nay. Neu nguoi dung yeu cau du bao, noi ro tinh nang da
  tat de uu tien do dung va goi y cac lua chon DU LIEU THAT: luy ke den ngay, so sanh ky lich su,
  KPI thuc dat so voi chi tieu da nhap, va thoi diem cap nhat du lieu. Chi tieu/ke hoach cua ky tuong
  lai da duoc con nguoi nhap san van la du lieu thuc te co the tra cuu; khong duoc bien no thanh du bao.
- Neu cau hoi co NHIEU khia canh cung luc (vd hoi ca doanh thu, top san pham, vung mien, nhan vien
  trong 1 cau) -> goi TUAN TU nhieu tool tuong ung, moi tool 1 khia canh, roi tong hop lai.
- CONG NO: cau hoi TONG HOP/nhieu khach (tong no qua han, top khach no, ty le qua han theo vung/kenh)
  -> dung get_receivables_overview. Cong no cua 1 khach cu the -> get_customer_detail. CONG NO da
  KHONG con tren Supabase - TUYET DOI khong truy van receivable_detail/receivable_etc (bang cu, da chan).
- Voi phan cau hoi KHONG thuoc cac nhom tren: thu query_database tren warehouse truoc neu schema da
  mo ta. Neu warehouse KHONG CO object/cot can thiet, BAT BUOC dung search_sql_server_catalog de tim
  trong TOAN BO SQL Server da duoc cap quyen, sau do dung query_sql_server (neu tool kha dung) de doc
  live. TUYET DOI KHONG noi "khong truy cap/khong den duoc du lieu" chi vi schema viet tay khong liet
  ke bang do; chi ket luan thieu sau khi da tim catalog va thu truy van, va phai noi ro loi that neu co.
  query_sql_server dung T-SQL (TOP, dbo.[Object]), query_database dung SQLite (LIMIT).
  Neu can boc tach cong no ad-hoc ngoai 2 tool cong no chuan, van uu tien fact_congno_khachhang trong
  warehouse vi day la snapshot da chuan hoa tu SP goc; khong tu EXEC stored procedure bat ky.
- TON KHO snapshot Supabase cu chi dung khi cau hoi dung pham vi bang inventory da xac nhan. Neu hoi
  table/view ton kho khac tren Bravo, tim catalog SQL Server; khong tu suy dien months_to_sell.
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
  khac va tra theo CHI SO KHAC: V15/V22/V25 (tien do theo cac moc ngay), ASO (khach hang hoat dong),
  thuong quy va thuong nam. Bac, nguong va hieu luc cu the PHAI doc bang get_salary_bonus_policy,
  KHONG dung mot con so viet san trong prompt cho moi ky/vai tro. Luong co ban: tu 60% tro len
  van huong 100%, duoi 60% moi bi cat ty le. => Nguoi duoi 65% VAN CO THE duoc V15/ASO va VAN huong
  du luong co ban. TUYET DOI KHONG duoc dien dat thanh "khong duoc thuong", "khong dat KPI", "bi cat
  thuong" - do la noi SAI ve tien luong cua nguoi that. Chi duoc noi dung pham vi: "chua toi muc
  thuong nhom hang". He thong co so V15/V22/V25/ASO DA CHOT trong FACT_ThongKeTinhLuong; dung
  get_salary_detail/get_salary_ranking de doc so thuc te, dung get_salary_bonus_policy de giai thich.
  Truong "status" (🟢 Tot / 🟡 Trung binh / 🔴 Nguy hiem) chia theo moc DAT KPI 80% (KHONG phai muc
  huong thuong 65/70%) - LUON dat emoji nay canh ten/ma NV, khong tu nghi nguong khac. Vi du dung:
  "TDV Nguyen Van A dat 67% chi tieu - da toi muc thuong nhom hang cua TDV (65%) nhung CHUA dat KPI
  (80%), va chua dat chi tieu 100%". Voi QLV dat 67% thi VAN duoi cong thuong nhom hang 70%.
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

THOI DIEM DU LIEU:
- Backend se tu gan nguon, moc du lieu, moc dong bo va canh bao do moi sau khi cau tra loi hoan tat.
- KHONG tu viet dong "Du lieu cap nhat den...", KHONG chep timestamp tu lich su hoi thoai va KHONG
  doan thoi diem dong bo. Chi tong hop noi dung nghiep vu tu ket qua tool.
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


def _tool_call_key(name: str, tool_input: dict) -> str:
    """Van tay on dinh de khong chay lai cung tool+cung tham so trong mot cau hoi."""
    return f"{name}:{json.dumps(tool_input or {}, sort_keys=True, ensure_ascii=False, default=str)}"


_FORCE_FINAL_ANSWER = (
    "Dung goi them cong cu. Hay tra loi CUOI CUNG ngay tu du lieu da lay. "
    "Khong duoc noi 'cau hoi qua phuc tap'. Neu du lieu chua du de ket luan, neu CHINH XAC phan nao "
    "da doi chieu duoc, phan nao con thieu hoac nguon nao bi dut; khong hien bang trung gian nhu ket "
    "qua cuoi va khong bia so."
)


def _response_text(response) -> str:
    return "".join(block.text for block in response.content if block.type == "text").strip()


def _dynamic_context_note(question: str = "", session_id: str = "", scope_area_code: str = None,
                           scope_employee_code: str = None, scope_channel: str = None) -> str:
    """Phan DONG cua system prompt (ngay du lieu + ngu canh doi theo tung cau hoi) - tach rieng khoi
    phan tinh de KHONG lam vo cache (kho local dong bo lai moi 15-30 phut, glossary/query-state doi
    theo tung cau hoi nen KHONG the cache chung voi schema/rules tinh)."""
    latest = latest_data_date()
    parts = [f'Ngay co du lieu moi nhat trong kho hien tai: {latest} (dung lam moc cho "hom nay"/'
             f'"gan day" neu nguoi dung khong noi ro ngay; kho local co the tre toi da ~15-30 phut so voi Bravo that).']

    parts.append(
        "Backend tu gan footer do moi theo dung nguon da truy van. Model KHONG duoc lap lai timestamp "
        "trong lich su hoac tu viet dong 'Du lieu cap nhat den'."
    )

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

    try:
        live_schema = relevant_schema_context(question)
        if live_schema:
            parts.append(live_schema)
    except Exception as exc:
        # Catalog dong la tang mo rong. Neu VPN/metadata tam loi, cac tool chuan va
        # warehouse van phai hoat dong; model co the goi tool search de thu lai.
        parts.append(f"Catalog SQL Server tam thoi chua nap duoc: {str(exc)[:180]}")

    return "\n\n".join(parts)


def _blocked_future_forecast_response(question: str, session_id: str, query_id: str = None) -> dict:
    """Tra loi fail-closed truoc khi tao client AI hay cham vao bat ky CSDL nao."""
    append_message(session_id, "user", question, query_id=query_id)
    append_message(session_id, "assistant", FUTURE_FORECAST_DISABLED_MESSAGE, query_id=query_id)
    return {
        "answer": FUTURE_FORECAST_DISABLED_MESSAGE,
        "sql_used": [],
        "last_result": None,
        "freshness": [],
        "query_id": query_id,
        "feature_disabled": True,
    }


def ask(question: str, session_id: str = "default", username: str = None, scope_area_code: str = None,
        scope_employee_code: str = None, scope_channel: str = None, scope_role: str = None,
        query_id: str = None) -> dict:
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
    if is_future_forecast_question(question):
        return _blocked_future_forecast_response(question, session_id, query_id)

    api_key = (os.environ.get("LLM_API_KEY", "").strip()
               or os.environ.get("ANTHROPIC_API_KEY", "").strip())
    if not api_key or api_key == "mock-key-for-local-testing":
        answer_text = "⚠️ **Chưa cấu hình API Key Claude/Anthropic**: Vui lòng bổ sung biến `ANTHROPIC_API_KEY=sk-ant-api03...` vào file `backend/.env` để khởi chạy tính năng Phân tích Dữ liệu AI."
        append_message(session_id, "user", question, query_id=query_id)
        append_message(session_id, "assistant", answer_text, query_id=query_id)
        return {
            "answer": answer_text,
            "sql_used": [],
            "last_result": None,
            "freshness": [],
            "query_id": query_id,
        }

    freshness = FreshnessCollector()
    client = _llm_client()
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
    seen_tool_calls = set()
    unique_tool_calls = 0

    # Tai khoan bi gioi han vung: loai han tool SQL tu do khoi danh sach gui cho AI (AI KHONG CO KHA
    # NANG goi, khong chi la "duoc dan dung goi") - chi con lai cac tool bao cao chuan da kiem soat
    # duoc filter vung o tang code.
    tools_for_request = _tools_for_request(scope_area_code, scope_channel, scope_role)

    # System tach 2 block: block TINH (rules+schema) danh cache_control TTL 1h - it doi nen cache-hit
    # cao, chi tinh ~10% gia input goc; block DONG (ngay du lieu, glossary, query-state, few-shot, scope)
    # KHONG cache vi doi theo tung cau hoi/tai khoan.
    system_blocks = [
        {"type": "text", "text": _static_system_prompt(), "cache_control": {"type": "ephemeral", "ttl": "1h"}},
        {"type": "text", "text": _dynamic_context_note(question, session_id, scope_area_code, scope_employee_code, scope_channel)},
    ]

    # 06/08/2026: GO BO output_config={"effort": "medium"} (them 05/08) sau khi do tren du lieu that.
    # Effort thap khien model suy luan nong hon MOI luot nen phai di NHIEU VONG tool hon moi ra dap an,
    # Truoc day model cham tran tool roi roi vao nhanh fallback "cau hoi qua phuc tap":
    #   - ty le nguoi dung nhan cau tu choi: 0,5% (2/384, 20/07-04/08) -> 27,0% (10/37, 06/08)
    #   - ty le cham tran 4 vong: 8,2% -> 37,1%; phan bo so lenh goi don dong dung tai moc 4
    # Muc hien tai cho phep nhieu vong hon, chan lap tool va bat buoc tong hop khi dung lai.
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
            answer_text = freshness.finalize_answer(answer_text)
            append_message(session_id, "user", question, query_id=query_id)
            append_message(session_id, "assistant", answer_text, query_id=query_id)
            if last_tool_used:
                set_query_state(session_id, last_tool_used[0], last_tool_used[1])
            if ran_adhoc_query:
                save_example(*ran_adhoc_query)
            return {"answer": answer_text, "sql_used": sql_used, "last_result": last_result,
                    "freshness": freshness.as_dicts(),
                    "query_id": query_id}

        tool_results = []
        original_tool_uses = [b for b in resp.content if b.type == "tool_use"]
        # Gop cac lenh goi cung tool + cung tham so phu thanh mot (xem _merge_bulk_tool_calls - da tach
        # ra ngoai de test duoc, va da va 2 loi gay mat du lieu am tham vao 10/08/2026).
        merged_sub_ids = _merge_bulk_tool_calls(original_tool_uses)

        executed_count = 0
        new_tools_this_round = 0
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

            tool_key = _tool_call_key(tu.name, tu.input)
            if tool_key in seen_tool_calls:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({
                        "note": "Lenh nay da chay voi dung tham so trong cau hoi hien tai. Hay dung ket qua da co va tong hop, khong goi lai."
                    }),
                })
                continue
            if unique_tool_calls >= MAX_UNIQUE_TOOL_CALLS:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({
                        "note": f"Da du {MAX_UNIQUE_TOOL_CALLS} truy van khac nhau. Hay tong hop cau tra loi tu du lieu da co."
                    }),
                })
                continue

            seen_tool_calls.add(tool_key)
            unique_tool_calls += 1
            new_tools_this_round += 1
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
                elif tu.name == "search_sql_server_catalog":
                    payload = search_sql_catalog(
                        tu.input.get("query", question),
                        limit=tu.input.get("limit", 6),
                        include_definition=tu.input.get("include_definition", True),
                    )
                else:
                    payload = {"error": f"Tool khong ro: {tu.name}"}
            elif tu.name in RAW_SQL_TOOLS:
                if scope_area_code or scope_channel:
                    # Phong ho: tool nay khong con trong tools_for_request nen AI khong the goi duoc,
                    # nhung neu vi ly do gi van xuat hien thi tu choi thang, KHONG thuc thi SQL.
                    sql_used.append(f"[BI CHAN - tai khoan gioi han] {tu.name}")
                    payload = {"error": "Tai khoan cua ban bi gioi han (vung/kenh), khong duoc dung truy van SQL tu do."}
                elif tu.name in LIVE_SQL_TOOL_NAMES and scope_role not in LIVE_SQL_ALLOWED_ROLES:
                    sql_used.append(f"[BI CHAN - vai tro khong duoc query SQL live] {tu.name}")
                    payload = {"error": "Tai khoan khong duoc phep truy van SQL Server live tu do."}
                else:
                    db = RAW_SQL_TOOLS[tu.name]
                    sql = tu.input.get("sql", "")
                    sql_used.append(f"[{db}] {sql}")
                    result = run_query(sql, question=question, db=db, username=username, session_id=session_id)
                    last_result = result
                    last_tool_used = (tu.name, str(tu.input))
                    if result.get("ok"):
                        freshness.record_raw(db, result, sql)
                    if db == "local" and result["ok"]:
                        ran_adhoc_query = (question, sql)
                    payload = _raw_query_payload(result, db, question)
            else:
                sql_used.append(f"[bao cao chuan] {tu.name}({tu.input})")
                tresult = call_template(tu.name, tu.input, question=question, username=username, session_id=session_id,
                                         scope_area_code=scope_area_code, scope_employee_code=scope_employee_code,
                                         scope_channel=scope_channel, scope_role=scope_role)
                last_result = tresult
                last_tool_used = (tu.name, str(tu.input))
                if tresult.get("ok"):
                    freshness.record_template(
                        tu.name, tresult["result"], args=tu.input, scope_channel=scope_channel
                    )
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
        if new_tools_this_round == 0:
            break

    # Cham tran/no-progress: cam goi them tool va bat model tong hop tu bang chung da co. Khong tra
    # cau "qua phuc tap" nua, va khong dua bang trung gian ra Excel nhu the la ket qua cuoi.
    if messages and messages[-1].get("role") == "user" and isinstance(messages[-1].get("content"), list):
        messages[-1]["content"].append({"type": "text", "text": _FORCE_FINAL_ANSWER})
    else:
        messages.append({"role": "user", "content": _FORCE_FINAL_ANSWER})
    final_resp = client.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS, system=system_blocks,
        messages=messages, extra_headers=_CACHE_BETA_HEADERS,
    )
    compute_and_log_cost(final_resp.usage, MODEL, question, session_id, username)
    fallback = _response_text(final_resp) or (
        "Toi da doi chieu cac nguon du lieu nhung chua du bang chung de ket luan chinh xac. "
        "Ket qua trung gian da duoc an de tranh hieu nham la bao cao cuoi."
    )
    fallback = freshness.finalize_answer(fallback)
    append_message(session_id, "user", question, query_id=query_id)
    append_message(session_id, "assistant", fallback, query_id=query_id)
    return {"answer": fallback, "sql_used": sql_used, "last_result": None,
            "freshness": freshness.as_dicts(),
            "partial_results_hidden": True, "query_id": query_id}


def ask_stream(question: str, session_id: str = "default", username: str = None, scope_area_code: str = None,
                scope_employee_code: str = None, scope_channel: str = None, scope_role: str = None,
                query_id: str = None):
    """11/08/2026: BAN SSE cua ask() - GIONG HET logic tool-calling/phan quyen/cache o tren.
    17/08/2026: SDK van nhan stream tu model, nhung backend chi cong bo text sau khi biet response
    khong con tool_use, loai timestamp model tu sinh va gan metadata nguon. Uu tien answer tren UI
    trung khop 100% voi answer luu lich su; khong lo doan tong hop trung gian ra ngoai.

    Transport model van dung stream de khong doi timeout/SDK, nhung SSE chi phat cau tra loi da chot
    sau khi backend xu ly footer. Day la ham GENERATOR (dung yield) - goi ham nay tra ve 1 generator,
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
    if is_future_forecast_question(question):
        blocked = _blocked_future_forecast_response(question, session_id, query_id)
        yield {"type": "text_delta", "text": blocked["answer"]}
        yield {"type": "done", **blocked}
        return

    api_key = (os.environ.get("LLM_API_KEY", "").strip()
               or os.environ.get("ANTHROPIC_API_KEY", "").strip())
    if not api_key or api_key == "mock-key-for-local-testing":
        msg = ("⚠️ **Chưa cấu hình API Key Claude/Anthropic**: Vui lòng bổ sung biến "
               "`ANTHROPIC_API_KEY=sk-ant-api03...` vào file `backend/.env` để khởi chạy tính năng "
               "Phân tích Dữ liệu AI.")
        append_message(session_id, "user", question, query_id=query_id)
        append_message(session_id, "assistant", msg, query_id=query_id)
        yield {"type": "text_delta", "text": msg}
        yield {"type": "done", "answer": msg, "sql_used": [], "last_result": None,
               "freshness": [],
               "query_id": query_id}
        return

    freshness = FreshnessCollector()
    client = _llm_client()
    history = load_history(session_id, max_turns=MAX_HISTORY_TURNS)
    messages = list(history) + [{"role": "user", "content": question}]
    _last_msg_cache_block = None  # xem ghi chu day du o ask()

    sql_used = []
    last_result = None
    last_tool_used = None
    ran_adhoc_query = None
    seen_tool_calls = set()
    unique_tool_calls = 0

    tools_for_request = _tools_for_request(scope_area_code, scope_channel, scope_role)

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
            for _event in stream:
                # Khong day text ra UI truoc khi biet response co tool_use hay khong. Backend can
                # loai footer timestamp model tu sinh va gan dung metadata nguon truoc khi cong bo.
                pass
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
                    for _event in stream2:
                        pass
                    resp2 = stream2.get_final_message()
                compute_and_log_cost(resp2.usage, MODEL, question, session_id, username)
                answer_text = "".join(b.text for b in resp2.content if b.type == "text").strip()
                if not answer_text:
                    answer_text = ("Xin lỗi, dữ liệu trả về quá lớn để tổng hợp gọn trong 1 câu trả lời. "
                                    "Bạn thử hỏi cụ thể/thu hẹp phạm vi hơn giúp mình nhé (vd theo vùng, theo thời gian ngắn hơn).")
            answer_text = freshness.finalize_answer(answer_text)
            yield {"type": "text_delta", "text": answer_text}
            append_message(session_id, "user", question, query_id=query_id)
            append_message(session_id, "assistant", answer_text, query_id=query_id)
            if last_tool_used:
                set_query_state(session_id, last_tool_used[0], last_tool_used[1])
            if ran_adhoc_query:
                save_example(*ran_adhoc_query)
            yield {"type": "done", "answer": answer_text, "sql_used": sql_used,
                   "last_result": last_result, "freshness": freshness.as_dicts(),
                   "query_id": query_id}
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
        new_tools_this_round = 0
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

            tool_key = _tool_call_key(tu.name, tu.input)
            if tool_key in seen_tool_calls:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({
                        "note": "Lenh nay da chay voi dung tham so trong cau hoi hien tai. Hay dung ket qua da co va tong hop, khong goi lai."
                    }),
                })
                continue
            if unique_tool_calls >= MAX_UNIQUE_TOOL_CALLS:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps({
                        "note": f"Da du {MAX_UNIQUE_TOOL_CALLS} truy van khac nhau. Hay tong hop cau tra loi tu du lieu da co."
                    }),
                })
                continue

            seen_tool_calls.add(tool_key)
            unique_tool_calls += 1
            new_tools_this_round += 1
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
                elif tu.name == "search_sql_server_catalog":
                    payload = search_sql_catalog(
                        tu.input.get("query", question),
                        limit=tu.input.get("limit", 6),
                        include_definition=tu.input.get("include_definition", True),
                    )
                else:
                    payload = {"error": f"Tool khong ro: {tu.name}"}
            elif tu.name in RAW_SQL_TOOLS:
                if scope_area_code or scope_channel:
                    sql_used.append(f"[BI CHAN - tai khoan gioi han] {tu.name}")
                    payload = {"error": "Tai khoan cua ban bi gioi han (vung/kenh), khong duoc dung truy van SQL tu do."}
                elif tu.name in LIVE_SQL_TOOL_NAMES and scope_role not in LIVE_SQL_ALLOWED_ROLES:
                    sql_used.append(f"[BI CHAN - vai tro khong duoc query SQL live] {tu.name}")
                    payload = {"error": "Tai khoan khong duoc phep truy van SQL Server live tu do."}
                else:
                    db = RAW_SQL_TOOLS[tu.name]
                    sql = tu.input.get("sql", "")
                    sql_used.append(f"[{db}] {sql}")
                    result = run_query(sql, question=question, db=db, username=username, session_id=session_id)
                    last_result = result
                    last_tool_used = (tu.name, str(tu.input))
                    if result.get("ok"):
                        freshness.record_raw(db, result, sql)
                    if db == "local" and result["ok"]:
                        ran_adhoc_query = (question, sql)
                    payload = _raw_query_payload(result, db, question)
            else:
                sql_used.append(f"[bao cao chuan] {tu.name}({tu.input})")
                tresult = call_template(tu.name, tu.input, question=question, username=username, session_id=session_id,
                                         scope_area_code=scope_area_code, scope_employee_code=scope_employee_code,
                                         scope_channel=scope_channel, scope_role=scope_role)
                last_result = tresult
                last_tool_used = (tu.name, str(tu.input))
                if tresult.get("ok"):
                    freshness.record_template(
                        tu.name, tresult["result"], args=tu.input, scope_channel=scope_channel
                    )
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
        if new_tools_this_round == 0:
            break

    if messages and messages[-1].get("role") == "user" and isinstance(messages[-1].get("content"), list):
        messages[-1]["content"].append({"type": "text", "text": _FORCE_FINAL_ANSWER})
    else:
        messages.append({"role": "user", "content": _FORCE_FINAL_ANSWER})
    with client.messages.stream(
        model=MODEL, max_tokens=MAX_TOKENS, system=system_blocks,
        messages=messages, extra_headers=_CACHE_BETA_HEADERS,
    ) as final_stream:
        for _event in final_stream:
            pass
        final_resp = final_stream.get_final_message()
    compute_and_log_cost(final_resp.usage, MODEL, question, session_id, username)
    fallback = _response_text(final_resp) or (
        "Toi da doi chieu cac nguon du lieu nhung chua du bang chung de ket luan chinh xac. "
        "Ket qua trung gian da duoc an de tranh hieu nham la bao cao cuoi."
    )
    fallback = freshness.finalize_answer(fallback)
    yield {"type": "text_delta", "text": fallback}
    append_message(session_id, "user", question, query_id=query_id)
    append_message(session_id, "assistant", fallback, query_id=query_id)
    yield {"type": "done", "answer": fallback, "sql_used": sql_used, "last_result": None,
           "freshness": freshness.as_dicts(),
           "partial_results_hidden": True, "query_id": query_id}
