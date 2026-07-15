import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Get all customers in MB ETC
cur.execute("""
    SELECT h."CustomerCode", k."Name", SUM(h."TotalAmount") as amt
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    WHERE h."IsActive" = TRUE
      AND t."AreaCode" = 'MB'
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY h."CustomerCode", k."Name"
    ORDER BY amt DESC
""")
rows = cur.fetchall()

# We want to see if subset sums to 4,114,726,789
target_diff = 4114726789
print(f"Target discrepancy: {target_diff:,.0f}")

print("\nTop MB ETC customers:")
for r in rows[:15]:
    print(f"  {r[0]} | {r[1][:40]} | {r[2]:,.0f}")

# Let's try combining the top non-hospital accounts to see if they sum to target_diff
# Việt Đức: 1,436,118,489
# Thiên Thành: 673,915,278
# Mỹ Đức: 666,076,068
# Thanh Sơn: 340,128,571
# VADPHARMA: 197,668,582
# Viện Y Học Biển: 155,711,239
# Khách không lấy hóa đơn: 127,375,427
# Bán lẻ tại Kho: 86,161,681
# Phòng khám Tâm Phúc: 80,508,085
# Youngone: 64,608,397
# Lạc Việt: 47,037,448
# PQA: 43,219,029
# Viện Y Học Cổ Truyền Quân Đội: 39,428,571
# Tân Thời Đại: 18,620,000
# Nhi Thịnh: 18,274,286
# Bán lẻ và Nội bộ: 14,198,016
# Hà Thành: 11,885,714
# Nhà thuốc Chu Giáp: 6,857,143
# Y - Dược KDH: 5,736,190
# Nhà thuốc Nguyên Khang: 5,485,714
# Y Dược Bích Đào: 5,097,714
# Dược phẩm Liên Mai: 4,114,286
# Y Dược Đình Cự: 4,114,286
# Tâm Anh: 3,714,286
# Phát triển y học Việt: 3,360,000
# Nhà thuốc Khánh Phương: 3,257,143
# Nhà thuốc An Sinh: 3,257,142
# Nhà thuốc 1A+: 3,085,714
# Nhà thuốc Dũng Hoa: 2,857,143
# Nhật Minh: 2,451,428
# Nhà thuốc Hương Cải: 1,954,286
# Nhà thuốc Hương Cải I: 1,954,286
# Bán lẻ và Nội bộ (another): 185,714
# Nhà thuốc Minh Tiến: 990,476
# Bệnh viện phổi Bắc Ninh 2: 1,337,143 (this has Bệnh viện in name, let's keep it)

# Let's sum the non-hospital ones:
non_hospitals = [
    1436118489, 673915278, 666076068, 340128571, 197668582, 
    127375427, 86161681, 80508085, 64608397, 47037448, 
    43219029, 18620000, 18274286, 14198016, 11885714, 
    6857143, 5736190, 5485714, 5097714, 4114286, 
    4114286, 3714286, 3360000, 3257143, 3257142, 
    3085714, 2857143, 2451428, 1954286, 1954286, 
    990476, 185714
]
print(f"Sum of selected non-hospitals: {sum(non_hospitals):,.0f}")
# Wait, 3,781,424,424.
# How about:
# Let's write a code to find if there is a subset of customers that sums to EXACTLY 4,114,726,789 or extremely close.

conn.close()
