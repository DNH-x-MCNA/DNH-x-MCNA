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
MAX_TOOL_ROUNDS = 8  # gioi han so lan model duoc goi lai tool trong 1 cau hoi (tranh loop vo han)
MAX_ROWS_TO_MODEL = 50  # chi gui toi da 50 dong ket qua ve cho model doc, tranh ton token
MAX_TOKENS = 8192  # du du cho ca "thinking" (Sonnet 5 tu bat mac dinh) lan text tra loi cuoi cung,
                    # tranh truong hop thinking an het ngan sach lam text tra ve rong
MAX_HISTORY_TURNS = 10  # so cap hoi-dap gan nhat duoc nho lai trong 1 session

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
                        "UU TIEN dung tool nay cho moi cau hoi ve san pham ban chay/top san pham.",
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
        "description": "Doanh thu theo vung mien (Mien Bac/Trung/Nam), gop ca OTC+ETC, trong 1 khoang ngay. "
                        "BAT BUOC dung tool nay cho MOI cau hoi ve doanh thu theo vung/mien/khu vuc - KE CA "
                        "KHI nguoi dung chi hoi 1 vung cu the (vd 'doanh thu mien Nam'): van goi tool nay "
                        "(no luon tra ve ca 3 vung) roi CHI trich/hien thi vung duoc hoi trong cau tra loi, "
                        "TUYET DOI KHONG tu viet SQL rieng voi dieu kien area_code=... vi se BO SOT khach "
                        "hang 'mo coi' (khong co ho so trong bang khach hang) ma CHI ham nay moi suy luan "
                        "dung vung qua tien to ma khach hang.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "get_employee_kpi",
        "description": "KPI nhan vien tinh tu snapshot gan nhat <= as_of_date - LUON tra ve san so luong "
                        "total_employees/count_below_target/count_above_target (khong can lay het danh sach moi biet tong quan). "
                        "NGUONG DAT KPI LA 80% (khong phai 100%). Moi dong ket qua co san truong 'status' "
                        "(🟢 Tot = pct>=80, 🟡 Trung binh = 50-79%, 🔴 Nguy hiem = <50%) - LUON hien thi nguyen "
                        "gia tri status nay kem ten/ma NV trong cau tra loi, KHONG tu tinh nguong mau khac. "
                        "UU TIEN dung tool nay cho moi cau hoi ve KPI/doanh so nhan vien/sales. "
                        "Voi cau hoi 'ai chua dat KPI/target' -> dung filter='below_target' (KHONG dung limit lon roi tu loc thu cong, "
                        "gay ton du lieu va co the khong tra loi duoc). "
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
                           "description": "'all'=top N tot nhat (mac dinh), 'below_target'=CHUA dat KPI (pct<80, te nhat truoc), 'above_target'=DA dat KPI (pct>=80, tot nhat truoc)"},
                "position_code": {"type": "string", "description": "Loc theo vai tro cu the: TDV/QLV/CTV/CS/TP/PP/TBP/TK (khong bat buoc - de trong neu hoi chung tat ca vai tro)"},
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
                "position_code": {"type": "string", "description": "Loc theo vai tro: TDV/QLV/CTV/CS/TP/PP/TBP/TK (khong bat buoc)"},
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
        "description": "Cay doanh thu/KPI 3 cap: Truong phong/GD mien -> QLV -> Trinh duoc vien, dung "
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
        "CHI dung cho cau hoi ve TON KHO (inventory) hoac CONG NO (receivable_detail/receivable_etc) - "
        "day la du lieu do dong nghiep tu nhap, CHI CO tren Supabase, Bravo KHONG CO nguon tuong duong. "
        "Chay 1 cau SQL SELECT (chi doc) tren Supabase (PostgreSQL - ten cot phan biet hoa/thuong, "
        "PHAI dat trong dau ngoac kep \"...\"). Chi duoc dung SELECT/WITH, khong duoc INSERT/UPDATE/DELETE/DROP."
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
- Neu cau hoi thuoc 1 trong 14 nhom: doanh thu theo kenh, top san pham, top khach hang, doanh thu
  theo vung mien, KPI/doanh so nhan vien (tong quan/thang), KPI THEO NGAY 1 nhan vien ca nhan, SO SANH
  2 khoang thoi gian, CHI TIET 1 khach hang cu the, TRA CUU ma/ten/vai tro nhan vien, KIEM TRA don hang
  bat thuong/chay don KPI, TON KHO THEO VUNG, LICH SU DOI QLV, CAY DOANH THU/KPI TP-QLV-TDV, XEP HANG
  KPI -> BAT BUOC dung tool tuong ung (get_revenue_by_channel, get_top_products, get_top_customers,
  get_revenue_by_region, get_employee_kpi, get_employee_daily_kpi, compare_periods, get_customer_detail,
  get_employee_directory, check_order_timing, get_inventory_by_region, get_qlv_change_history,
  get_revenue_tree, get_kpi_ranking).
  Day la cac truy van DA DUOC KIEM CHUNG khop voi du lieu goc, KHONG tu sinh SQL thay the.
- Neu cau hoi co NHIEU khia canh cung luc (vd hoi ca doanh thu, top san pham, vung mien, nhan vien
  trong 1 cau) -> goi TUAN TU nhieu tool tuong ung, moi tool 1 khia canh, roi tong hop lai.
- Voi phan cau hoi KHONG thuoc 14 nhom tren: neu la ve CONG NO -> dung query_inventory_receivables
  (Supabase). Con lai (hoa don/doanh thu/san pham/khach hang/nhan vien/vung mien dang ad-hoc, tra hang...)
  -> dung query_database (kho local SQLite).
- Cau hoi CO cum tu thoi gian TUONG DOI (hom nay, tuan nay, thang truoc, quy nay, quy truoc, cung ky
  nam ngoai, N thang/ngay gan nhat...) -> BAT BUOC goi resolve_relative_date TRUOC de lay khoang ngay
  cu the, roi moi dung ket qua do lam date_from/date_to cho tool khac - TUYET DOI KHONG tu suy luan
  ngay thang, de tranh nham quy/thang. Neu resolve_relative_date bao loi (khong nhan dien duoc cum
  tu), hoi lai nguoi dung ngay/khoang ngay cu the thay vi doan bua.
- Neu nguoi dung dinh nghia 1 thuat ngu nghiep vu moi trong cau hoi (vd "doanh thu rong la doanh thu
  tru chiet khau") -> goi save_business_term de luu lai, roi tiep tuc tra loi cau hoi nhu binh thuong.
- Voi KPI nhan vien TONG QUAN/xep hang/nhieu nhan vien cung luc (ke ca ma khu vuc nhu MBKV*, ASM*):
  dung get_employee_kpi, nguong DAT KPI la 80% (khong phai 100%). Ket qua da co san truong "status"
  (🟢 Tot / 🟡 Trung binh / 🔴 Nguy hiem) - LUON dat emoji nay canh ten/ma NV, khong tu nghi nguong khac.
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

QUAN TRONG VE DO DAI CAU TRA LOI (tiet kiem chi phi - moi token output deu tinh tien):
- Tra loi NGAN GON, DI THANG vao so lieu - KHONG mo dau dai dong, KHONG nhac lai cau hoi, KHONG giai
  thich lai nhung gi tool da tra ve neu nguoi dung khong hoi "tai sao"/"giai thich".
  neu chi 1 con so thi neu ro con so + don vi + ngu canh (vd "ngay nao", "khach hang nao") trong 1-2 cau,
  KHONG viet thanh doan van dai. Neu ket qua co nhieu dong, dung BANG (markdown table) thay vi mo ta
  bang loi van. Chi mo rong nhan xet/phan tich khi nguoi dung hoi ro "vi sao"/"nhan xet"/"danh gia".
- Neu tool tra ve loi hoac khong co du lieu phu hop, noi ngan gon cho nguoi dung, khong doan bua.
"""


def _dynamic_context_note(question: str = "", session_id: str = "", scope_area_code: str = None,
                           scope_employee_code: str = None, scope_channel: str = None) -> str:
    """Phan DONG cua system prompt (ngay du lieu + ngu canh doi theo tung cau hoi) - tach rieng khoi
    phan tinh de KHONG lam vo cache (kho local dong bo lai moi 15-30 phut, glossary/query-state doi
    theo tung cau hoi nen KHONG the cache chung voi schema/rules tinh)."""
    latest = latest_data_date()
    parts = [f'Ngay co du lieu moi nhat trong kho hien tai: {latest} (dung lam moc cho "hom nay"/'
             f'"gan day" neu nguoi dung khong noi ro ngay; kho local co the tre toi da ~15-30 phut so voi Bravo that).']

    # 20/07/2026: kiem tra RIENG tien trinh sync co con song khong (khac dong tren - chi biet ngay
    # du lieu, khong bat duoc sync treo/loi khi trung cuoi tuan/le khong co hoa don moi de lo ra).
    freshness_warning = sync_freshness_note()
    if freshness_warning:
        parts.append(freshness_warning)

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
        scope_employee_code: str = None, scope_channel: str = None) -> dict:
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
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    history = load_history(session_id, max_turns=MAX_HISTORY_TURNS)
    messages = list(history) + [{"role": "user", "content": question}]

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

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_blocks,
            tools=tools_for_request,
            messages=messages,
            extra_headers=_CACHE_BETA_HEADERS,
        )
        compute_and_log_cost(resp.usage, MODEL, question, session_id)
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            answer_text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not answer_text:
                # Truong hop hy huu: het ngan sach token cho phan suy luan (thinking) khien khong con
                # cho phan text tra ve - thu lai 1 lan voi yeu cau tra loi ngay, ngan gon.
                messages.append({"role": "user", "content": "Hay tra loi ngay bay gio, ngan gon truc tiep."})
                resp2 = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=system_blocks,
                                                tools=tools_for_request, messages=messages,
                                                extra_headers=_CACHE_BETA_HEADERS)
                compute_and_log_cost(resp2.usage, MODEL, question, session_id)
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
        for tu in tool_uses:
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
                    result = run_query(sql, question=question, db=db, username=username)
                    last_result = result
                    last_tool_used = (tu.name, str(tu.input))
                    if db == "local" and result["ok"]:
                        ran_adhoc_query = (question, sql)
                    payload = ({"columns": result["columns"], "rows": result["rows"][:MAX_ROWS_TO_MODEL],
                                "row_count": result["row_count"]} if result["ok"] else {"error": result["error"]})
            else:
                sql_used.append(f"[bao cao chuan] {tu.name}({tu.input})")
                tresult = call_template(tu.name, tu.input, question=question, username=username,
                                         scope_area_code=scope_area_code, scope_employee_code=scope_employee_code,
                                         scope_channel=scope_channel)
                last_result = tresult
                last_tool_used = (tu.name, str(tu.input))
                payload = tresult["result"] if tresult["ok"] else {"error": tresult["error"]}
                # 22/07/2026 (diem #5): tool co the kem canh bao tu-doi-chieu (vd tong theo vung lech
                # tong tho). TRUOC DAY chi lay ["result"] nen canh bao BI ROI MAT truoc khi toi model
                # -> nguoi dung van nhan so lieu sai ma khong he biet. Chi boc them khi CO canh bao;
                # truong hop binh thuong giu nguyen hinh dang cu (khong lam nhieu prompt).
                if tresult.get("canh_bao"):
                    payload = {"du_lieu": payload,
                               "CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG": tresult["canh_bao"]}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": str(payload),
            })

        messages.append({"role": "user", "content": tool_results})

    fallback = "Xin loi, cau hoi qua phuc tap can nhieu buoc truy van, vui long hoi cu the hon."
    append_message(session_id, "user", question)
    append_message(session_id, "assistant", fallback)
    return {"answer": fallback, "sql_used": sql_used, "last_result": last_result}
