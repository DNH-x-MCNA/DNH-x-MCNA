import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Test the correct query where we join each table first
cur.execute("""
    WITH otc_sales AS (
        SELECT 
            'OTC' AS "Channel",
            t."AreaCode" AS "Region",
            h."TotalAmount",
            h."DocStatus",
            h."EInvoiceStatus",
            h."IsActive",
            h."DocDate"
        FROM brv_hoadonhdr h
        JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
        JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
        WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
    ),
    etc_sales AS (
        SELECT 
            'ETC' AS "Channel",
            t."AreaCode" AS "Region",
            h."TotalAmount",
            h."DocStatus",
            h."EInvoiceStatus",
            h."IsActive",
            h."DocDate"
        FROM brvsx_hoadonhdr h
        JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
        JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
        WHERE h."IsActive" = TRUE
          AND h."CustomerCode" NOT IN ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632')
    ),
    combined_sales AS (
        SELECT * FROM otc_sales
        UNION ALL
        SELECT * FROM etc_sales
    )
    SELECT
        c."Channel",
        c."Region",
        SUM(c."TotalAmount") AS "Revenue"
    FROM combined_sales c
    LEFT JOIN brv_trangthaiduyet d ON c."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON c."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND c."DocDate"::date >= '2026-06-01'
      AND c."DocDate"::date <= '2026-06-30'
    GROUP BY c."Channel", c."Region"
    ORDER BY c."Channel", c."Region"
""")
print("=== Refined Join Query Results ===")
total = 0
for r in cur.fetchall():
    print(f"  Channel={r[0]}, Region={r[1]}, Revenue={r[2]:,.0f}")
    total += r[2]
print(f"Total: {total:,.0f} (Expected: ~62 tỷ)")

conn.close()
