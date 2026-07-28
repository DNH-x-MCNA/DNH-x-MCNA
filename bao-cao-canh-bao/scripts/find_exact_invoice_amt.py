import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

cur.execute("""
    SELECT "CustomerCode", "TotalAmount", "DocDate", "BranchCode"
    FROM brv_hoadonhdr
    WHERE "IsActive" = TRUE AND "IsHC" = FALSE
      AND "DocDate"::date >= '2026-06-01' AND "DocDate"::date <= '2026-06-30'
      AND "TotalAmount" BETWEEN 59000000 AND 61000000
""")
print("=== OTC Invoices ~ 60M ===")
for r in cur.fetchall():
    print(f"  Cust={r[0]}, Amt={r[1]:,.0f}, Date={r[2]}, Branch={r[3]}")

conn.close()
