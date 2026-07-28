import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

cur.execute("""
    WITH raw_invoices AS (
        SELECT 
            h."CustomerCode", 
            h."TotalAmount", 
            h."DocStatus", 
            h."EInvoiceStatus", 
            h."IsActive", 
            h."DocDate", 
            h."BranchCode",
            'OTC' as source_table
        FROM brv_hoadonhdr h
        WHERE h."IsHC" = FALSE
        
        UNION ALL
        
        SELECT 
            h."CustomerCode", 
            h."TotalAmount", 
            h."DocStatus", 
            h."EInvoiceStatus", 
            h."IsActive", 
            h."DocDate", 
            h."BranchCode",
            'ETC' as source_table
        FROM brvsx_hoadonhdr h
        WHERE h."CustomerCode" NOT IN ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632')
    ),
    joined_invoices AS (
        SELECT 
            r.*,
            COALESCE(k_otc."KenhBH", k_etc."KenhBH") as cust_kenh,
            COALESCE(k_otc."CityId", k_etc."CityId") as city_id
        FROM raw_invoices r
        LEFT JOIN dms_khachhang k_otc ON r."CustomerCode" = k_otc."Code" AND r.source_table = 'OTC'
        LEFT JOIN dmssx_khachhang k_etc ON r."CustomerCode" = k_etc."Code" AND r.source_table = 'ETC'
    ),
    valid_invoices AS (
        SELECT 
            j.*,
            t."AreaCode" as region,
            CASE 
                WHEN j.cust_kenh = 'OTC' THEN 'OTC'
                WHEN j.cust_kenh = 'ETC' THEN 'ETC'
                ELSE j.source_table
            END as final_channel
        FROM joined_invoices j
        JOIN dim_tinhthanhpho t ON j.city_id = t."CityId"
        LEFT JOIN brv_trangthaiduyet d ON j."DocStatus" = d."DocStatusKey"
        LEFT JOIN brv_trangthaihoadon e ON j."EInvoiceStatus" = e."EInvoiceStatusKey"
        WHERE j."IsActive" = TRUE
          AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
          AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
          AND j."DocDate"::date >= '2026-06-01' AND j."DocDate"::date <= '2026-06-30'
    )
    SELECT 
        final_channel,
        region,
        SUM("TotalAmount") as amt
    FROM valid_invoices
    GROUP BY final_channel, region
    ORDER BY final_channel, region
""")

print("=== Classifying Channel by Customer KenhBH ===")
total = 0
for r in cur.fetchall():
    print(f"  Channel={r[0]}, Region={r[1]}, Revenue={r[2]:,.0f}")
    total += r[2]
print(f"Total: {total:,.0f}")

conn.close()
