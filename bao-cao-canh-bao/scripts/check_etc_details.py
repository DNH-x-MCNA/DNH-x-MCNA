import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# 1. SubBranchCode
cur.execute("""
    SELECT "SubBranchCode", COUNT(*), SUM("TotalAmount")
    FROM brvsx_hoadonhdr
    WHERE "IsActive" = TRUE
      AND "DocDate"::date >= '2026-06-01' AND "DocDate"::date <= '2026-06-30'
    GROUP BY "SubBranchCode"
""")
print("=== SubBranchCode breakdown ===")
for r in cur.fetchall():
    print(f"  SubBranch={r[0]}, count={r[1]}, sum={r[2]:,.0f}")

# 2. WarehouseCode
cur.execute("""
    SELECT "WarehouseCode", COUNT(*), SUM("TotalAmount")
    FROM brvsx_hoadonhdr
    WHERE "IsActive" = TRUE
      AND "DocDate"::date >= '2026-06-01' AND "DocDate"::date <= '2026-06-30'
    GROUP BY "WarehouseCode"
""")
print("\n=== WarehouseCode breakdown ===")
for r in cur.fetchall():
    print(f"  Warehouse={r[0]}, count={r[1]}, sum={r[2]:,.0f}")

# 3. Top 10 customers in MB ETC
cur.execute("""
    SELECT h."CustomerCode", k."Name", SUM(h."TotalAmount") as amt
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    WHERE h."IsActive" = TRUE
      AND t."AreaCode" = 'MB'
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY h."CustomerCode", k."Name"
    ORDER BY amt DESC
    LIMIT 15
""")
print("\n=== Top 15 ETC Customers in MB for June 2026 ===")
for r in cur.fetchall():
    print(f"  CustCode={r[0]}, Name={r[1][:50] if r[1] else 'None'}, Amount={r[2]:,.0f}")

conn.close()
