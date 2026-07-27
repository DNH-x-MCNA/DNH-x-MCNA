# -*- coding: utf-8 -*-
"""
SPIKE CHAN (ke hoach tuan T5, muc 1.0) - CHAY TREN MAY CHU LIVE `C:\\dnh_chatbot`.

Muc dich: truoc khi viet bat ky dong code R-B nao, xac nhan TAI KHOAN BRAVO CUA CHATBOT
(bien moi truong BRAVO_* trong .env cua chatbot, KHAC BRAVO_SQL_* ben D:\\DNH) co the:
  1. Ket noi dung database chua SP usp_DeptAccDueDate_GetData.
  2. Co quyen EXECUTE tren SP do.
  3. Thoi gian chay bao lau (quyet dinh thiet ke lich dong bo - muc 1.3):
        < 20s  -> goi trong main() throttle 60 phut, khong can lich rieng.
        > 60s  -> them --congno-only, lich rieng timeout 300s.

Chi doc (SP chi tao temp table), co rollback() trong finally -> an toan tuyet doi voi Bravo.

Chay:  py spike_congno_sp.py
"""
import sys, os, time, datetime as dt

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    for line in open(env_path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


load_env()

from query_engine import _get_engine  # dung DUNG engine "bravo" cua chatbot (BRAVO_* env)


def main():
    print("=" * 70)
    print("SPIKE cong no SP - tai khoan Bravo CUA CHATBOT")
    print("=" * 70)
    print(f"BRAVO_SERVER   = {os.environ.get('BRAVO_SERVER')}")
    print(f"BRAVO_DATABASE = {os.environ.get('BRAVO_DATABASE')}")
    print(f"BRAVO_USER     = {os.environ.get('BRAVO_USER')}")
    print("-" * 70)

    engine = _get_engine("bravo")
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()

        # 0) Xac nhan dang tro dung server/database nao (KHAC nhau se giai thich moi le lech)
        cur.execute("SELECT @@SERVERNAME, DB_NAME(), SUSER_SNAME(), CURRENT_USER")
        srv, dbn, login, cu = cur.fetchone()
        print(f"@@SERVERNAME = {srv}")
        print(f"DB_NAME()    = {dbn}")
        print(f"login        = {login}")
        print(f"CURRENT_USER = {cu}")
        print("-" * 70)

        # 1) SP nam o database nao? (ke hoach ghi NH_Report_TM.dbo.usp_DeptAccDueDate_GetData)
        cur.execute(
            "SELECT DB_NAME(), s.name, o.name, o.type_desc "
            "FROM sys.objects o JOIN sys.schemas s ON o.schema_id = s.schema_id "
            "WHERE o.name = 'usp_DeptAccDueDate_GetData'")
        found = cur.fetchall()
        if found:
            for r in found:
                print(f"SP TIM THAY: {r[0]}.{r[1]}.{r[2]} ({r[3]})")
        else:
            print("!! SP usp_DeptAccDueDate_GetData KHONG thay trong database hien tai.")
            print("   -> Kiem tra BRAVO_DATABASE co dung khong (ke hoach: NH_Report_TM).")
            print("   -> Neu SP o DB khac, chatbot phai tro dung DB do (hoac SP goi cross-db).")
        print("-" * 70)

        # 2) EXECUTE + timing (bat rieng loi thieu quyen)
        today = dt.datetime.now()
        d1 = dt.datetime(today.year, 1, 1).strftime("%Y-%m-%d")
        d2 = today.strftime("%Y-%m-%d")
        print(f"EXEC usp_DeptAccDueDate_GetData @_DocDate1={d1}, @_DocDate2={d2}, "
              f"@_Period1=7, @_Period2=15, @_RepType=1, @_IsPrepaymentInclude=1 ...")
        t0 = time.time()
        try:
            cur.execute(
                "EXEC dbo.usp_DeptAccDueDate_GetData "
                "@_DocDate1=?, @_DocDate2=?, @_Period1=?, @_Period2=?, @_RepType=?, @_IsPrepaymentInclude=?",
                d1, d2, 7, 15, 1, 1)
        except Exception as e:
            msg = str(e)
            print("!! EXEC THAT BAI.")
            print(f"   Loi: {msg[:400]}")
            if "EXECUTE permission" in msg or "permission was denied" in msg or "quyen" in msg.lower():
                print("   => THIEU QUYEN EXECUTE. Bao DNH cap quyen EXECUTE tren SP cho tai khoan chatbot.")
                print("      Phuong an lui: job ben D:\\DNH day ket qua SP len (xem muc 1.0 ke hoach).")
            raise

        # Duyet cac result set, chon set co ca CustomerCode va OverDueAmount
        setnum = 0
        target_cols, data = None, None
        while True:
            setnum += 1
            if cur.description is not None:
                cols = [d[0] for d in cur.description]
                has = "CustomerCode" in cols and "OverDueAmount" in cols
                print(f"  result set #{setnum}: {len(cols)} cot, la set cong no = {has}")
                if has and target_cols is None:
                    target_cols = cols
                    data = cur.fetchall()
            if not cur.nextset():
                break
        elapsed = time.time() - t0

        print("-" * 70)
        print(f">>> THOI GIAN CHAY SP: {elapsed:.1f}s")
        if elapsed < 20:
            print("    -> Thiet ke 1.3: goi trong main() throttle 60 phut (don gian nhat).")
        elif elapsed > 60:
            print("    -> Thiet ke 1.3: tach co --congno-only, lich rieng timeout 300s.")
        else:
            print("    -> Thiet ke 1.3: vung 20-60s, uu tien tach lich rieng cho an toan.")

        if target_cols is None:
            print("!! Khong tim thay result set cong no (co CustomerCode + OverDueAmount).")
            return
        ix = {n: i for i, n in enumerate(target_cols)}

        def s(col):
            i = ix.get(col)
            return sum((r[i] or 0) for r in data) if i is not None else None

        from collections import Counter
        ch = Counter(("OTC" if r[ix["ClassCode"]] == "TM" else "ETC") for r in data) if "ClassCode" in ix else {}

        print("-" * 70)
        print(f"So dong result set cong no : {len(data)}")
        print(f"So cot                     : {len(target_cols)}")
        print(f"Cac cot                    : {target_cols}")
        print(f"SUM CloseBal (tong du no)  : {s('CloseBal'):,.0f}" if 'CloseBal' in ix else "CloseBal: (khong co cot)")
        print(f"SUM OverDueAmount          : {s('OverDueAmount'):,.0f}" if 'OverDueAmount' in ix else "")
        for b in ("CloseBal5", "CloseBal6", "CloseBal7", "CloseBal8"):
            if b in ix:
                print(f"SUM {b:12s}          : {s(b):,.0f}")
        print(f"So dong theo kenh          : {dict(ch)}")
        print("-" * 70)
        print("OK - tai khoan chatbot chay duoc SP. Ghi lai cac so tren de doi chieu buoc 1.2.")
    finally:
        try:
            raw.rollback()  # bo moi thay doi temp-table, khong dung du lieu that
        except Exception:
            pass
        raw.close()


if __name__ == "__main__":
    main()