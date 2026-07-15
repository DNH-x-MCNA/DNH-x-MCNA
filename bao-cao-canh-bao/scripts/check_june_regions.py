import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# 1. OTC June 2026 by AreaCode
print('=== OTC June 2026 by AreaCode (IsHC = False) ===')
cur.execute("""
    SELECT t."AreaCode", SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY t."AreaCode"
    ORDER BY t."AreaCode"
""")
for r in cur.fetchall():
    print(f"  Area={r[0]}, Amount={r[1]:,.0f}")

# 2. Let's see the total OTC June 2026 without AreaCode join (to see if some customers don't join)
print('\n=== OTC June 2026 total (no client join) ===')
cur.execute("""
    SELECT SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
print(f"  Total: {cur.fetchone()[0]:,.0f}")

# 3. Check ETC June 2026 by AreaCode
print('\n=== ETC June 2026 by AreaCode (IsHC = False if applicable) ===')
cur.execute("""
    SELECT t."AreaCode", SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY t."AreaCode"
    ORDER BY t."AreaCode"
""")
for r in cur.fetchall():
    print(f"  Area={r[0]}, Amount={r[1]:,.0f}")

# 4. Let's see unique customer counts and check if some are missing or have wrong channel in dmssx_khachhang/dms_khachhang
# Wait! Let's check the date of the daily report. Slide 1 header:
# "Ngày 30/06/2026 - Nguồn: Data Warehouse"
# Wait! Is it possible that the dates in the database are not exactly June 2026?
# No, DocDate range was MIN: 2026-04-01, MAX: 2026-06-30.
# Wait! Let's see the sum of OTC TotalAmount for June 30, 2026 (Daily)!
print('\n=== OTC Daily 2026-06-30 by AreaCode ===')
cur.execute("""
    SELECT t."AreaCode", SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date = '2026-06-30'
    GROUP BY t."AreaCode"
""")
for r in cur.fetchall():
    print(f"  Area={r[0]}, Amount={r[1]:,.0f}")

# Let's see the sum of ETC TotalAmount for June 30, 2026 (Daily)!
print('\n=== ETC Daily 2026-06-30 by AreaCode ===')
cur.execute("""
    SELECT t."AreaCode", SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date = '2026-06-30'
    GROUP BY t."AreaCode"
""")
for r in cur.fetchall():
    print(f"  Area={r[0]}, Amount={r[1]:,.0f}")

conn.close()
