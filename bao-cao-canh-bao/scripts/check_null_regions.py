import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Check OTC
cur.execute("""
    SELECT h."CustomerCode", h."TotalAmount", k."CityId"
    FROM brv_hoadonhdr h
    JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
      AND t."CityId" IS NULL
""")
print("=== OTC Invoices with NULL Region ===")
for r in cur.fetchall():
    print(f"  Cust={r[0]}, Amt={r[1]:,.0f}, CityId={r[2]}")

# Check ETC
cur.execute("""
    SELECT h."CustomerCode", h."TotalAmount", k."CityId"
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    WHERE h."IsActive" = TRUE
      AND h."CustomerCode" NOT IN ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632')
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
      AND t."CityId" IS NULL
""")
print("\n=== ETC Invoices with NULL Region ===")
for r in cur.fetchall():
    print(f"  Cust={r[0]}, Amt={r[1]:,.0f}, CityId={r[2]}")

conn.close()
