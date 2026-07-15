import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

cur.execute("""
    SELECT h."CustomerCode", COUNT(*), SUM(h."TotalAmount") as amt
    FROM brvsx_hoadonhdr h
    LEFT JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    WHERE h."IsActive" = TRUE
      AND k."Code" IS NULL
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY h."CustomerCode"
    ORDER BY amt DESC
    LIMIT 15
""")
print("=== Unjoined Customers in ETC June 2026 ===")
for r in cur.fetchall():
    print(f"  CustCode={r[0]}, count={r[1]}, Amount={r[2]:,.0f}")

conn.close()
