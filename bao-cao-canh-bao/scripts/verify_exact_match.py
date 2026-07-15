import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

print("=== OTC June 2026 Verification ===")
# Raw with status
cur.execute("""
    SELECT SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
raw_otc = cur.fetchone()[0] or 0
print(f"  Raw total in brv_hoadonhdr (excl. IsHC & cancelled): {raw_otc:,.0f}")

# Joined with dms_khachhang
cur.execute("""
    SELECT SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
joined_otc = cur.fetchone()[0] or 0
print(f"  After joining with dms_khachhang (excl. P000001): {joined_otc:,.0f} (Slide 1: 32.66 tỷ)")


print("\n=== ETC June 2026 Verification ===")
# Raw with status
cur.execute("""
    SELECT SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
raw_etc = cur.fetchone()[0] or 0
print(f"  Raw total in brvsx_hoadonhdr (excl. cancelled): {raw_etc:,.0f}")

# Joined with dmssx_khachhang
cur.execute("""
    SELECT SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
joined_etc = cur.fetchone()[0] or 0
print(f"  After joining with dmssx_khachhang: {joined_etc:,.0f}")

# Excluded internal/non-operating codes (like Việt Đức, Thiên Thành, Mỹ Đức, Thanh Sơn...)
cur.execute("""
    SELECT SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
      AND h."CustomerCode" NOT IN ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632')
""")
excl_etc = cur.fetchone()[0] or 0
print(f"  After excluding 4 top dealers (Việt Đức, Thiên Thành, Mỹ Đức, Thanh Sơn): {excl_etc:,.0f} (Slide 1: 29.40 tỷ)")

conn.close()
