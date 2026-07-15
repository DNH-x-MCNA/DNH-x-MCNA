import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Get the exact list of MB ETC sales for each customer (non-wholesalers)
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

# Let's use subset sum search
def find_subsets(index, current_sum, current_list):
    if abs(current_sum - target) < 1.0: # Exact to the nearest integer
        print(f"Found EXACT MATCH: {current_list} = {current_sum:,.2f}")
        return True
    if current_sum > target + 1000000 or index >= len(rows):
        return False
        
    # Option 1: Include rows[index]
    incl = find_subsets(index + 1, current_sum + rows[index][2], current_list + [rows[index][0]])
    # Option 2: Exclude rows[index]
    excl = find_subsets(index + 1, current_sum, current_list)
    return incl or excl

print("Searching for exact subset...")
find_subsets(0, 0, [])
print("Done searching.")
