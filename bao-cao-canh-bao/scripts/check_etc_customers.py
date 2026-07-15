import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Query all ETC customers in MB for June 2026
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
""")
print("=== ETC Customers in MB for June 2026 ===")
total_mb = 0
for r in cur.fetchall():
    print(f"  CustCode={r[0]}, Name={r[1][:50] if r[1] else 'None'}, Amount={r[2]:,.0f}")
    total_mb += r[2]
print(f"Total MB ETC in DB: {total_mb:,.0f}")

conn.close()
