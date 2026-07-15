import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Get OTC valid invoices
cur.execute("""
    SELECT h."CustomerCode", k."Name", t."AreaCode", h."BranchCode", h."DistributorCode", h."TotalAmount"
    FROM brv_hoadonhdr h
    JOIN dms_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
otc_rows = cur.fetchall()

# Get ETC valid invoices
cur.execute("""
    SELECT h."CustomerCode", k."Name", t."AreaCode", h."BranchCode", h."DistributorCode", h."TotalAmount"
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
etc_rows = cur.fetchall()

# Slide 1 targets
# OTC MB: 20,874,510,792
# OTC MN: 7,589,505,689
# OTC MT: 4,203,754,295
# ETC MB: 16,117,144,383
# ETC MN: 12,034,109,791
# ETC MT: 1,245,536,633

print("=== OTC June 2026 Regional Sums ===")
for reg in ['MB', 'MN', 'MT']:
    s = sum(r[5] for r in otc_rows if r[2] == reg)
    print(f"  Region={reg} | Sum={s:,.0f}")

print("\n=== ETC June 2026 Regional Sums ===")
for reg in ['MB', 'MN', 'MT']:
    s = sum(r[5] for r in etc_rows if r[2] == reg)
    print(f"  Region={reg} | Sum={s:,.0f}")

# Let's check ETC MB without the wholesalers:
etc_mb_no_wholesalers = [r for r in etc_rows if r[2] == 'MB' and r[0] not in ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632')]
print(f"\nETC MB after excluding 4 wholesalers: {sum(r[5] for r in etc_mb_no_wholesalers):,.0f} (Target: 16,117,144,383)")
# Target difference: 16,442,424,788 - 16,117,144,383 = 325,280,405

# Let's print the customer codes and names in ETC MB no wholesalers that have sales in June
print("\nETC MB customer sales details:")
etc_mb_details = {}
for r in etc_mb_no_wholesalers:
    etc_mb_details[r[0]] = etc_mb_details.get(r[0], 0) + r[5]
for c, amt in sorted(etc_mb_details.items(), key=lambda x: x[1], reverse=True):
    print(f"  {c} | {amt:,.0f}")

conn.close()
