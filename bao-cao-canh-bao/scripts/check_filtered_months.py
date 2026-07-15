import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

print("=== OTC Invoices by Month (with cancel filter) ===")
cur.execute("""
    SELECT DATE_TRUNC('month', h."DocDate"::date) as m, COUNT(*), SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
      AND h."DocDate"::date >= '2026-01-01' AND h."DocDate"::date <= '2026-12-31'
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
    GROUP BY m
    ORDER BY m
""")
for r in cur.fetchall():
    print(f"  Month: {str(r[0])[:7]}, Count: {r[1]}, Sum: {r[2]:,.0f}")

print("\n=== ETC Invoices by Month (with cancel filter) ===")
cur.execute("""
    SELECT DATE_TRUNC('month', h."DocDate"::date) as m, COUNT(*), SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."CustomerCode" NOT IN ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632')
      AND h."DocDate"::date >= '2026-01-01' AND h."DocDate"::date <= '2026-12-31'
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
    GROUP BY m
    ORDER BY m
""")
for r in cur.fetchall():
    print(f"  Month: {str(r[0])[:7]}, Count: {r[1]}, Sum: {r[2]:,.0f}")

print("\n=== ETC by Month joining dmssx_khachhang (correct table) ===")
cur.execute("""
    SELECT DATE_TRUNC('month', h."DocDate"::date) as m, COUNT(*), SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."CustomerCode" NOT IN ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632')
      AND h."DocDate"::date >= '2026-01-01' AND h."DocDate"::date <= '2026-12-31'
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
    GROUP BY m
    ORDER BY m
""")
for r in cur.fetchall():
    print(f"  Month: {str(r[0])[:7]}, Count: {r[1]}, Sum: {r[2]:,.0f}")

print("\n=== OTC by Month joining dms_khachhang ===")
cur.execute("""
    SELECT DATE_TRUNC('month', h."DocDate"::date) as m, COUNT(*), SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
      AND h."DocDate"::date >= '2026-01-01' AND h."DocDate"::date <= '2026-12-31'
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
    GROUP BY m
    ORDER BY m
""")
for r in cur.fetchall():
    print(f"  Month: {str(r[0])[:7]}, Count: {r[1]}, Sum: {r[2]:,.0f}")

conn.close()
