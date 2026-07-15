import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Search for any invoice in June 2026 with TotalAmount = 326,600,000 or close
print("=== Invoices close to 326.6M or 311M ===")
cur.execute("""
    SELECT "CustomerCode", "TotalAmount", "DocDate", "BranchCode"
    FROM brvsx_hoadonhdr
    WHERE "IsActive" = TRUE
      AND "DocDate"::date >= '2026-06-01' AND "DocDate"::date <= '2026-06-30'
      AND "TotalAmount" BETWEEN 300000000 AND 350000000
""")
for r in cur.fetchall():
    print(f"  ETC Table: CustCode={r[0]}, Amount={r[1]:,.0f}, Date={r[2]}, Branch={r[3]}")

cur.execute("""
    SELECT "CustomerCode", "TotalAmount", "DocDate", "BranchCode"
    FROM brv_hoadonhdr
    WHERE "IsActive" = TRUE
      AND "DocDate"::date >= '2026-06-01' AND "DocDate"::date <= '2026-06-30'
      AND "TotalAmount" BETWEEN 300000000 AND 350000000
""")
for r in cur.fetchall():
    print(f"  OTC Table: CustCode={r[0]}, Amount={r[1]:,.0f}, Date={r[2]}, Branch={r[3]}")

conn.close()
