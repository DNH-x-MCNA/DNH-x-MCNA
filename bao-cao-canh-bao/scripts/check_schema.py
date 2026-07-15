import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# 1. Check DocDate range in brv_hoadonhdr (OTC)
print('=== OTC DocDate range ===')
cur.execute("""SELECT MIN("DocDate"), MAX("DocDate") FROM brv_hoadonhdr WHERE "IsActive" = TRUE""")
r = cur.fetchone()
print(f'  Min: {r[0]}, Max: {r[1]}')

# 2. Check DocDate range in brvsx_hoadonhdr (ETC)
print('\n=== ETC DocDate range ===')
cur.execute("""SELECT MIN("DocDate"), MAX("DocDate") FROM brvsx_hoadonhdr WHERE "IsActive" = TRUE""")
r = cur.fetchone()
print(f'  Min: {r[0]}, Max: {r[1]}')

# 3. Monthly OTC revenue breakdown
print('\n=== OTC Monthly Revenue (DATE_TRUNC) ===')
cur.execute("""
    SELECT DATE_TRUNC('month', h."DocDate"::timestamp) AS month, 
           COUNT(*) AS invoices,
           SUM(h."TotalAmount") AS revenue
    FROM brv_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
    GROUP BY month
    ORDER BY month
""")
for r in cur.fetchall():
    print(f'  Month: {r[0]}, Invoices: {r[1]}, Revenue: {r[2]:,.0f}')

# 4. Last 7 days OTC revenue
print('\n=== OTC Last 7 days Revenue ===')
cur.execute("""
    SELECT h."DocDate"::date AS day, COUNT(*) AS invoices, SUM(h."TotalAmount") AS revenue
    FROM brv_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= (SELECT MAX("DocDate"::date) FROM brv_hoadonhdr WHERE "IsActive" = TRUE) - INTERVAL '6 days'
    GROUP BY day
    ORDER BY day
""")
for r in cur.fetchall():
    print(f'  Day: {r[0]}, Invoices: {r[1]}, Revenue: {r[2]:,.0f}')

# 5. KPI to day 20 - cumulative OTC invoice revenue up to 20th of the month
print('\n=== OTC Revenue up to day 20 of June 2026 ===')
cur.execute("""
    SELECT SUM(h."TotalAmount") AS revenue_to_20
    FROM brv_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-20'
""")
r = cur.fetchone()
print(f'  OTC Revenue Jun 1-20: {r[0]:,.0f}')

# 6. Check SaveDate values in fact_tonghopkhachhang
print('\n=== fact_tonghopkhachhang SaveDate values ===')
cur.execute("""SELECT DISTINCT "SaveDate" FROM fact_tonghopkhachhang ORDER BY "SaveDate" """)
for r in cur.fetchall():
    print(f'  SaveDate: {r[0]}')

# 7. Check Amount_CT vs Amount_Cus
print('\n=== fact_tonghopkhachhang Amount_CT vs Amount_Cus sample ===')
cur.execute("""
    SELECT f."EmployeeCode", f."SaveDate", f."Amount_CT", f."Amount_Cus", f."MonthSaleTarget", f."CustomerCode"
    FROM fact_tonghopkhachhang f
    WHERE f."Amount_CT" IS NOT NULL AND f."Amount_CT" != 0
    LIMIT 5
""")
for r in cur.fetchall():
    print(f'  Emp={r[0]}, Date={r[1]}, Amount_CT={r[2]}, Amount_Cus={r[3]}, Target={r[4]}, Cust={r[5]}')

conn.close()
