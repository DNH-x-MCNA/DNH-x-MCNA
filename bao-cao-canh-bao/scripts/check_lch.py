import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

cur.execute("""
    SELECT k."LCH_FK", COUNT(*), SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    WHERE h."IsActive" = TRUE
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY k."LCH_FK"
""")
print("=== ETC June 2026 sales by LCH_FK ===")
for r in cur.fetchall():
    print(f"  LCH_FK={r[0]}, count={r[1]}, sum={r[2]:,.0f}")

# Let's check LCH_FK counts in dmssx_khachhang overall
cur.execute("""
    SELECT "LCH_FK", COUNT(*)
    FROM dmssx_khachhang
    GROUP BY "LCH_FK"
""")
print("\n=== LCH_FK overall counts ===")
for r in cur.fetchall():
    print(f"  LCH_FK={r[0]}, count={r[1]}")

conn.close()
