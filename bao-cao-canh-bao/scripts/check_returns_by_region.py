import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Get returns by region in June 2026
cur.execute("""
    SELECT t."AreaCode", SUM(r."TotalAmount0") as return_amt
    FROM brvsx_tralai r
    JOIN dmssx_khachhang k ON r."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    WHERE r."IsActive" = TRUE
      AND r."DocDate"::date >= '2026-06-01' AND r."DocDate"::date <= '2026-06-30'
    GROUP BY t."AreaCode"
""")
print("=== ETC Returns by Region in June 2026 ===")
for r in cur.fetchall():
    print(f"  Region: {r[0]}, Return Amount: {r[1]:,.0f}")

conn.close()
