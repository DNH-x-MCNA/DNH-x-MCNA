import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

cur.execute("""
    SELECT h."CustomerCode", SUM(h."TotalAmount") as amt
    FROM brvsx_hoadonhdr h
    LEFT JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
      AND k."Code" IS NULL
    GROUP BY h."CustomerCode"
    ORDER BY amt DESC
""")
print("=== Unjoined Customer Codes in June 2026 ETC ===")
for r in cur.fetchall():
    print(f"  Code: {r[0]}, Amount: {r[1]:,.0f}")

conn.close()
