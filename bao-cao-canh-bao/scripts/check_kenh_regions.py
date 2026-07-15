import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# 1. OTC June 2026 by AreaCode with KenhBH = 'OTC'
print("=== OTC June 2026 by AreaCode with KenhBH = 'OTC' ===")
cur.execute("""
    SELECT t."AreaCode", SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."IsHC" = FALSE
      AND k."KenhBH" = 'OTC'
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY t."AreaCode"
    ORDER BY t."AreaCode"
""")
for r in cur.fetchall():
    print(f"  Area={r[0]}, Amount={r[1]:,.0f}")

# 2. ETC June 2026 by AreaCode with KenhBH = 'ETC'
print("\n=== ETC June 2026 by AreaCode with KenhBH = 'ETC' ===")
cur.execute("""
    SELECT t."AreaCode", SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND k."KenhBH" = 'ETC'
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY t."AreaCode"
    ORDER BY t."AreaCode"
""")
for r in cur.fetchall():
    print(f"  Area={r[0]}, Amount={r[1]:,.0f}")

conn.close()
