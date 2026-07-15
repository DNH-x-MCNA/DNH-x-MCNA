import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

# Wait, the hostname has a typo in pooler.southeast-1. Use pooler.supabase.com
conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

print("=== Negative Invoice Amounts ===")
cur.execute("SELECT COUNT(*), SUM(\"TotalAmount\") FROM brv_hoadonhdr WHERE \"TotalAmount\" < 0 AND \"IsActive\" = TRUE")
cnt, amt = cur.fetchone()
print(f"  OTC Negative invoices: {cnt} count, Sum: {amt or 0:,.0f}")

cur.execute("SELECT COUNT(*), SUM(\"TotalAmount\") FROM brvsx_hoadonhdr WHERE \"TotalAmount\" < 0 AND \"IsActive\" = TRUE")
cnt, amt = cur.fetchone()
print(f"  ETC Negative invoices: {cnt} count, Sum: {amt or 0:,.0f}")

print("\n=== Checking OTC Return Invoices (tralai) ===")
# Check if there is any tralai table for OTC
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name LIKE '%tralai%'
""")
print(f"  Tralai tables: {[r[0] for r in cur.fetchall()]}")

print("\n=== MB ETC Customers with Sales in June 2026 ===")
cur.execute("""
    SELECT h."CustomerCode", k."Name", SUM(h."TotalAmount") as amt
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND t."AreaCode" = 'MB'
      AND h."CustomerCode" NOT IN ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632')
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY h."CustomerCode", k."Name"
    ORDER BY amt ASC
""")
rows = cur.fetchall()
for r in rows:
    print(f"  {r[0]} | {r[1][:40]} | {r[2]:,.0f}")

# Target difference in MB ETC is 16,442,424,788 - 16,117,144,383 = 325,280,405
target_diff = 325280405
print(f"\nTarget diff in MB ETC: {target_diff:,.0f}")

# Let's find if a single customer or combination matches target_diff
import itertools
print("Checking for single customer match...")
for r in rows:
    if abs(r[2] - target_diff) < 1000:
        print(f"  EXACT MATCH SINGLE: {r[0]} ({r[1]}) = {r[2]:,.0f}")

print("Checking for combinations of up to 3 customers matching target_diff...")
for k in range(1, 4):
    for comb in itertools.combinations(rows, k):
        s = sum(c[2] for c in comb)
        if abs(s - target_diff) < 1000:
            print(f"  EXACT MATCH COMBINATION: {[c[0] for c in comb]} = {s:,.0f}")

conn.close()
