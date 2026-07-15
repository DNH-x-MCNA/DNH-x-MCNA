import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Query ETC in MB for June 2026 and show matching vs non-matching keywords
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

hospital_keywords = ['Bệnh viện', 'BỆNH VIỆN', 'Bệnh Viện', 'Trung tâm', 'TRUNG TÂM', 'Trạm', 'TRẠM', 'Trại', 'TRẠI', 'Công an', 'CÔNG AN', 'TY tế', 'Y tế', 'Y TẾ', 'Phòng khám', 'PHÒNG KHÁM', 'Trường', 'TRƯỜNG', 'Học viện', 'HỌC VIỆN']

hospital_sum = 0
other_sum = 0

print("=== Non-hospital accounts in MB ETC ===")
for r in cur.fetchall():
    code = r[0]
    name = r[1] if r[1] else ''
    amt = r[2]
    
    is_hospital = False
    for kw in hospital_keywords:
        if kw in name:
            is_hospital = True
            break
            
    if is_hospital:
        hospital_sum += amt
    else:
        other_sum += amt
        print(f"  CustCode={code}, Name={name[:60]}, Amount={amt:,.0f}")

print(f"\nHospital/Clinic Sum: {hospital_sum:,.0f}")
print(f"Other/Distributor Sum: {other_sum:,.0f}")
print(f"Total: {hospital_sum + other_sum:,.0f}")

conn.close()
