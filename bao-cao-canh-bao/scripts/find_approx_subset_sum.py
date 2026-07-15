import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

cur.execute("""
    SELECT h."CustomerCode", k."Name", SUM(h."TotalAmount") as amt
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND t."AreaCode" = 'MB'
      AND h."CustomerCode" NOT IN ('HNO04012', 'HNO03889', 'HNO03973', 'HDU00632')
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY h."CustomerCode", k."Name"
""")
rows = cur.fetchall()
conn.close()

target = 325280405
print(f"Target: {target:,.0f}")

# Sort rows descending
rows = sorted(rows, key=lambda x: x[2], reverse=True)

# Find combinations that are within 500 VND of target
import itertools
print("Searching for subset within 500 VND...")
found = False

# We can use a recursive branch and bound with tolerance
def find_subsets_approx(index, current_sum, current_list):
    global found
    if abs(current_sum - target) < 500:
        print(f"Approx Match: {current_list} = {current_sum:,.2f} (diff={current_sum-target:,.2f})")
        found = True
        return
    if current_sum > target + 500 or index >= len(rows):
        return
        
    # Include
    find_subsets_approx(index + 1, current_sum + rows[index][2], current_list + [rows[index][0]])
    # Exclude
    find_subsets_approx(index + 1, current_sum, current_list)

find_subsets_approx(0, 0, [])
print(f"Finished searching. Found: {found}")
