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
from report_templates import call_template, latest_data_date
from conversation_memory import load_history, append_message

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
                        "UU TIEN dung tool nay cho moi cau hoi ve doanh thu theo vung/mien/khu vuc.",
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
        "description": "KPI THEO NGAY cho 1 nhan vien BAN HANG CA NHAN (co ma truc tiep tren hoa don, "
                        "vd 'tungtx') trong 1 thang. Target 1 ngay = 4% MonthSaleTarget cua nhan vien do "
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
                "employee_code": {"type": "string", "description": "Ma nhan vien ban hang ca nhan, vd 'tungtx' (KHONG dung ma khu vuc)"},
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

RAW_SQL_TOOLS = {"query_database": "local", "query_inventory_receivables": "supabase"}

ALL_TOOLS = TEMPLATE_TOOLS + [QUERY_TOOL, QUERY_SUPABASE_TOOL]
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
- Neu cau hoi thuoc 1 trong 10 nhom: doanh thu theo kenh, top san pham, top khach hang, doanh thu
  theo vung mien, KPI/doanh so nhan vien (tong quan/thang), KPI THEO NGAY 1 nhan vien ca nhan, SO SANH
  2 khoang thoi gian, CHI TIET 1 khach hang cu the, TRA CUU ma/ten/vai tro nhan vien, KIEM TRA don hang
  bat thuong/chay don KPI -> BAT BUOC dung tool tuong ung (get_revenue_by_channel, get_top_products,
  get_top_customers, get_revenue_by_region, get_employee_kpi, get_employee_daily_kpi, compare_periods,
  get_customer_detail, get_employee_directory, check_order_timing).
  Day la cac truy van DA DUOC KIEM CHUNG khop voi du lieu goc, KHONG tu sinh SQL thay the.
- Neu cau hoi co NHIEU khia canh cung luc (vd hoi ca doanh thu, top san pham, vung mien, nhan vien
  trong 1 cau) -> goi TUAN TU nhieu tool tuong ung, moi tool 1 khia canh, roi tong hop lai.
- Voi phan cau hoi KHONG thuoc 10 nhom tren: neu la ve TON KHO/CONG NO -> dung query_inventory_receivables
  (Supabase). Con lai (hoa don/doanh thu/san pham/khach hang/nhan vien/vung mien dang ad-hoc, tra hang...)
  -> dung query_database (kho local SQLite).
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


def _dynamic_context_note() -> str:
    """Phan DONG cua system prompt (moc ngay du lieu moi nhat) - tach rieng khoi phan tinh de KHONG
    lam vo cache (kho local dong bo lai moi 15-30 phut nen gia tri nay doi lien tuc trong ngay)."""
    latest = latest_data_date()
    return (f'Ngay co du lieu moi nhat trong kho hien tai: {latest} (dung lam moc cho "hom nay"/'
            f'"gan day" neu nguoi dung khong noi ro ngay; kho local co the tre toi da ~15-30 phut so voi Bravo that).')


def ask(question: str, session_id: str = "default", username: str = None) -> dict:
    """
    Nhan cau hoi tieng Viet + session_id (1 phien chat webapp) - tu dong nho lai vai cau hoi/tra loi
    gan nhat trong CUNG session de hieu ngu canh cau hoi tiep theo.
    Tra ve dict: {answer: str, sql_used: [list mo ta cac tool/SQL da chay], last_result: {...} hoac None}
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    history = load_history(session_id, max_turns=MAX_HISTORY_TURNS)
    messages = list(history) + [{"role": "user", "content": question}]

    sql_used = []
    last_result = None
    # System tach 2 block: block TINH (rules+schema) danh cache_control TTL 1h - it doi nen cache-hit
    # cao, chi tinh ~10% gia input goc; block DONG (ngay du lieu moi nhat) KHONG cache vi doi moi 15-30p.
    system_blocks = [
        {"type": "text", "text": _static_system_prompt(), "cache_control": {"type": "ephemeral", "ttl": "1h"}},
        {"type": "text", "text": _dynamic_context_note()},
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_blocks,
            tools=ALL_TOOLS_CACHED,
            messages=messages,
            extra_headers=_CACHE_BETA_HEADERS,
        )
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            answer_text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not answer_text:
                # Truong hop hy huu: het ngan sach token cho phan suy luan (thinking) khien khong con
                # cho phan text tra ve - thu lai 1 lan voi yeu cau tra loi ngay, ngan gon.
                messages.append({"role": "user", "content": "Hay tra loi ngay bay gio, ngan gon truc tiep."})
                resp2 = client.messages.create(model=MODEL, max_tokens=MAX_TOKENS, system=system_blocks,
                                                tools=ALL_TOOLS_CACHED, messages=messages,
                                                extra_headers=_CACHE_BETA_HEADERS)
                answer_text = "".join(b.text for b in resp2.content if b.type == "text").strip()
                if not answer_text:
                    answer_text = ("Xin lỗi, dữ liệu trả về quá lớn để tổng hợp gọn trong 1 câu trả lời. "
                                    "Bạn thử hỏi cụ thể/thu hẹp phạm vi hơn giúp mình nhé (vd theo vùng, theo thời gian ngắn hơn).")
            append_message(session_id, "user", question)
            append_message(session_id, "assistant", answer_text)
            return {"answer": answer_text, "sql_used": sql_used, "last_result": last_result}

        tool_results = []
        for tu in tool_uses:
            if tu.name in RAW_SQL_TOOLS:
                db = RAW_SQL_TOOLS[tu.name]
                sql = tu.input.get("sql", "")
                sql_used.append(f"[{db}] {sql}")
                result = run_query(sql, question=question, db=db, username=username)
                last_result = result
                payload = ({"columns": result["columns"], "rows": result["rows"][:MAX_ROWS_TO_MODEL],
                            "row_count": result["row_count"]} if result["ok"] else {"error": result["error"]})
            else:
                sql_used.append(f"[bao cao chuan] {tu.name}({tu.input})")
                tresult = call_template(tu.name, tu.input, question=question, username=username)
                last_result = tresult
                payload = tresult["result"] if tresult["ok"] else {"error": tresult["error"]}

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
