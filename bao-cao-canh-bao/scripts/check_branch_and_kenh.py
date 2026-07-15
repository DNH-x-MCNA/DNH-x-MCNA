import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Check KenhBH of customers in brv_hoadonhdr (OTC table)
cur.execute("""
    SELECT k."KenhBH", SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY k."KenhBH"
""")
print("=== Customers in OTC Table (brv_hoadonhdr) by KenhBH ===")
for r in cur.fetchall():
    print(f"  KenhBH: {r[0]}, Amount: {r[1]:,.0f}")

# Check KenhBH of customers in brvsx_hoadonhdr (ETC table)
cur.execute("""
    SELECT k."KenhBH", SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY k."KenhBH"
""")
print("\n=== Customers in ETC Table (brvsx_hoadonhdr) by KenhBH ===")
for r in cur.fetchall():
    print(f"  KenhBH: {r[0]}, Amount: {r[1]:,.0f}")

conn.close()
