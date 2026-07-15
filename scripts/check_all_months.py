import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

print("=== OTC Invoices by Month in 2026 ===")
cur.execute("""
    SELECT DATE_TRUNC('month', "DocDate"::date) as m, COUNT(*), SUM("TotalAmount")
    FROM brv_hoadonhdr
    WHERE "IsActive" = TRUE AND "IsHC" = FALSE
      AND "DocDate"::date >= '2026-01-01' AND "DocDate"::date <= '2026-12-31'
    GROUP BY m
    ORDER BY m
""")
for r in cur.fetchall():
    print(f"  Month: {r[0]}, Count: {r[1]}, Sum: {r[2]:,.0f}")

print("\n=== ETC Invoices by Month in 2026 ===")
cur.execute("""
    SELECT DATE_TRUNC('month', "DocDate"::date) as m, COUNT(*), SUM("TotalAmount")
    FROM brvsx_hoadonhdr
    WHERE "IsActive" = TRUE
      AND "CustomerCode" NOT IN ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632')
      AND "DocDate"::date >= '2026-01-01' AND "DocDate"::date <= '2026-12-31'
    GROUP BY m
    ORDER BY m
""")
for r in cur.fetchall():
    print(f"  Month: {r[0]}, Count: {r[1]}, Sum: {r[2]:,.0f}")

conn.close()
