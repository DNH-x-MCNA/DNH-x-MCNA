import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Search in OTC
cur.execute("""
    SELECT h."CustomerCode", k."Name", t."AreaCode", SUM(h."TotalAmount") as amt
    FROM brv_hoadonhdr h
    JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY h."CustomerCode", k."Name", t."AreaCode"
    HAVING SUM(h."TotalAmount") BETWEEN 58000000 AND 62000000
""")
print("=== OTC Customers with sales ~ 60M ===")
for r in cur.fetchall():
    print(f"  Code: {r[0]} | Name: {r[1][:40]} | Region: {r[2]} | Amount: {r[3]:,.0f}")

conn.close()
