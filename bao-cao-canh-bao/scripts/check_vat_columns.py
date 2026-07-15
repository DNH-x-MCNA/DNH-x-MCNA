import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Check columns starting with Total or Amt in brv_hoadonhdr
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'brv_hoadonhdr' AND column_name LIKE '%Amount%'")
print(f"brv_hoadonhdr Amount columns: {[r[0] for r in cur.fetchall()]}")

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'brvsx_hoadonhdr' AND column_name LIKE '%Amount%'")
print(f"brvsx_hoadonhdr Amount columns: {[r[0] for r in cur.fetchall()]}")

# Check if there is a TotalAmount0 or similar in any of the tables
cur.execute("""
    SELECT "TotalAmount", "BranchCode"
    FROM brv_hoadonhdr
    WHERE "IsActive" = TRUE AND "IsHC" = FALSE
      AND "DocDate"::date >= '2026-06-01' AND "DocDate"::date <= '2026-06-30'
    LIMIT 5
""")
print("\nSample brv_hoadonhdr amounts:")
for r in cur.fetchall():
    print(f"  Amt: {r[0]:,.0f}, Branch: {r[1]}")

conn.close()
