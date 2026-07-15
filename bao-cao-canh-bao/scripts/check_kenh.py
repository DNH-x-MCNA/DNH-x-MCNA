import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# 1. dms_khachhang KenhBH values
cur.execute('SELECT "KenhBH", COUNT(*) FROM dms_khachhang GROUP BY "KenhBH"')
print("=== dms_khachhang KenhBH counts ===")
for r in cur.fetchall():
    print(f"  KenhBH={r[0]}, count={r[1]}")

# 2. dmssx_khachhang KenhBH values
cur.execute('SELECT "KenhBH", COUNT(*) FROM dmssx_khachhang GROUP BY "KenhBH"')
print("\n=== dmssx_khachhang KenhBH counts ===")
for r in cur.fetchall():
    print(f"  KenhBH={r[0]}, count={r[1]}")

# 3. Sum total revenue for OTC June 2026 by KenhBH of customer
print("\n=== OTC June 2026 sales by customer KenhBH ===")
cur.execute("""
    SELECT k."KenhBH", COUNT(*), SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    WHERE h."IsActive" = TRUE
      AND h."IsHC" = FALSE
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY k."KenhBH"
""")
for r in cur.fetchall():
    print(f"  KenhBH={r[0]}, count={r[1]}, sum={r[2]:,.0f}")

# 4. Sum total revenue for ETC June 2026 by KenhBH of customer
print("\n=== ETC June 2026 sales by customer KenhBH ===")
cur.execute("""
    SELECT k."KenhBH", COUNT(*), SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    WHERE h."IsActive" = TRUE
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY k."KenhBH"
""")
for r in cur.fetchall():
    print(f"  KenhBH={r[0]}, count={r[1]}, sum={r[2]:,.0f}")

conn.close()
