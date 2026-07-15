import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# 1. fact_tonghopkhachhang AreaCode breakdown for June 2026
print("=== fact_tonghopkhachhang AreaCode breakdown for June 2026 ===")
cur.execute("""
    SELECT "AreaCode", SUM("Amount_Cus"), SUM("Amount_CT")
    FROM fact_tonghopkhachhang
    WHERE "SaveDate" = '2026-06-30T00:00:00'
    GROUP BY "AreaCode"
""")
for r in cur.fetchall():
    ac = r[0]
    cus = r[1] if r[1] is not None else 0
    ct = r[2] if r[2] is not None else 0
    print(f"  AreaCode={ac}, Amount_Cus={cus:,.0f}, Amount_CT={ct:,.0f}")

# 2. Check if we join with dim_nhanvien, what is the breakdown by PositionCode and IsDuplicate for June 2026
print("\n=== fact_tonghopkhachhang breakdown by PositionCode and IsDuplicate for June 2026 ===")
cur.execute("""
    SELECT n."PositionCode", COALESCE(n."IsDuplicate", 0) as is_dup, SUM(f."Amount_Cus")
    FROM fact_tonghopkhachhang f
    JOIN dim_nhanvien n ON f."EmployeeCode" = n."EmployeeCode"
    WHERE f."SaveDate" = '2026-06-30T00:00:00'
    GROUP BY n."PositionCode", COALESCE(n."IsDuplicate", 0)
""")
for r in cur.fetchall():
    pos = r[0]
    is_dup = r[1]
    amt = r[2] if r[2] is not None else 0
    print(f"  Position={pos}, IsDuplicate={is_dup}, Amount_Cus={amt:,.0f}")

# 3. Check ETC revenue in brvsx_hoadonhdr for June 2026
print("\n=== ETC June 2026 Revenue (brvsx_hoadonhdr) ===")
cur.execute("""
    SELECT SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
print(f"  ETC June 2026: {cur.fetchone()[0]:,.0f}")

# 4. Total OTC (brv_hoadonhdr) + ETC (brvsx_hoadonhdr) June 2026
otc_val = 39252070950
etc_val = 102022920618 # wait, let's see what the previous ETC June print returns
print(f"\nOTC direct sum: {otc_val:,.0f}")

conn.close()
