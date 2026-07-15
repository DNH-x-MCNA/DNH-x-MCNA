import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Query ETC returns
cur.execute("""
    SELECT t."AreaCode", SUM(r."TotalAmount0")
    FROM brvsx_tralai r
    JOIN dmssx_khachhang k ON r."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    WHERE r."IsActive" = TRUE
      AND r."DocDate"::date >= '2026-06-01' AND r."DocDate"::date <= '2026-06-30'
    GROUP BY t."AreaCode"
""")
print("ETC Returns June 2026 by AreaCode:")
for r in cur.fetchall():
    print(f"  Area={r[0]}, Amount={r[1]:,.0f}")

# Query OTC returns (if any - brv_tralai or similar? Let's check tables list first if needed)
# Wait, let's see if brv_tralai exists
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_name = 'brv_tralai'")
print("\nDoes brv_tralai exist?", cur.fetchone())

conn.close()
