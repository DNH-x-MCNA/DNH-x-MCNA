import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# 1. Total active OTC invoices in June 2026
cur.execute("""
    SELECT COUNT(*), SUM("TotalAmount")
    FROM brv_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
tot_cnt, tot_amt = cur.fetchone()
print(f"Total OTC active invoices in June 2026: cnt={tot_cnt}, amt={tot_amt:,.0f}")

# 2. Joined with dms_khachhang
cur.execute("""
    SELECT COUNT(*), SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
j1_cnt, j1_amt = cur.fetchone()
print(f"Joined with dms_khachhang: cnt={j1_cnt}, amt={j1_amt:,.0f} (diff={tot_amt - j1_amt:,.0f})")

# 3. Joined with UNION of dms_khachhang and dmssx_khachhang
cur.execute("""
    WITH combined_customers AS (
        SELECT "Code", "CityId" FROM dms_khachhang
        UNION
        SELECT "Code", "CityId" FROM dmssx_khachhang
    )
    SELECT COUNT(*), SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    JOIN combined_customers k ON h."CustomerCode" = k."Code"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
j2_cnt, j2_amt = cur.fetchone()
print(f"Joined with combined customers: cnt={j2_cnt}, amt={j2_amt:,.0f} (diff={tot_amt - j2_amt:,.0f})")

# 4. Check if some customer codes exist in combined_customers but have CityId as NULL or dim_tinhthanhpho join fails
cur.execute("""
    WITH combined_customers AS (
        SELECT "Code", "CityId" FROM dms_khachhang
        UNION
        SELECT "Code", "CityId" FROM dmssx_khachhang
    )
    SELECT COUNT(*), SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    JOIN combined_customers k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
j3_cnt, j3_amt = cur.fetchone()
print(f"Joined with combined customers + dim_tinhthanhpho: cnt={j3_cnt}, amt={j3_amt:,.0f} (diff={tot_amt - j3_amt:,.0f})")

# 5. Let's see some unmatched customer codes in June 2026
cur.execute("""
    SELECT DISTINCT h."CustomerCode", SUM(h."TotalAmount") as amt
    FROM brv_hoadonhdr h
    LEFT JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."IsHC" = FALSE
      AND k."Code" IS NULL
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY h."CustomerCode"
    ORDER BY amt DESC
    LIMIT 10
""")
print("\nUnmatched CustomerCodes in dms_khachhang:")
for r in cur.fetchall():
    print(f"  CustCode={r[0]}, Amount={r[1]:,.0f}")

conn.close()
