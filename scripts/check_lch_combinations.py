import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# We will test a few combinations:
# Combination A: LCH_FK IN (100072, 100075, 100089)
# Combination B: LCH_FK IN (100072, 100075, 100089, 100079)
# Combination C: LCH_FK IN (100072, 100075, 100089, 100079, 100090, 100071)
# Combination D: All except LCH_FK IN (100070, 100083, 100084, 100069, 100076)

combinations = {
    "A (Hospitals only: 72, 75, 89)": [100072, 100075, 100089],
    "B (Hospitals + Ward Stations: 72, 75, 89, 79)": [100072, 100075, 100089, 100079],
    "C (Hospitals + Stations + Clinics: 72, 75, 89, 79, 90, 71)": [100072, 100075, 100089, 100079, 100090, 100071],
    "D (Hospitals + Stations + Clinics + chains: 72, 75, 89, 79, 90, 71, 87)": [100072, 100075, 100089, 100079, 100090, 100071, 100087]
}

for name, lch_keys in combinations.items():
    print(f"\n==================================================")
    print(f"Testing Combination: {name}")
    print(f"==================================================")
    
    cur.execute("""
        SELECT t."AreaCode", SUM(h."TotalAmount")
        FROM brvsx_hoadonhdr h
        JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
        JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
        WHERE h."IsActive" = TRUE
          AND k."LCH_FK" IN (%s)
          AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
        GROUP BY t."AreaCode"
        ORDER BY t."AreaCode"
    """ % ",".join([str(x) for x in lch_keys]))
    
    tot = 0
    for r in cur.fetchall():
        print(f"  Area={r[0]}, Amount={r[1]:,.0f}")
        tot += r[1]
    print(f"  Total ETC: {tot:,.0f}")

# Let's also check if we filter by Customer Name containing certain keywords (our previous check)
# Let's see what the sum is for each region using keyword filtering
print(f"\n==================================================")
print(f"Testing Combination: Keyword filtering (Hospital-like only)")
print(f"==================================================")
cur.execute("""
    SELECT t."AreaCode", k."Name", h."TotalAmount"
    FROM brvsx_hoadonhdr h
    JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    WHERE h."IsActive" = TRUE
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")

hospital_keywords = ['Bệnh viện', 'BỆNH VIỆN', 'Bệnh Viện', 'Trung tâm', 'TRUNG TÂM', 'Trạm', 'TRẠM', 'Trại', 'TRẠI', 'Công an', 'CÔNG AN', 'Y tế', 'Y TẾ', 'Phòng khám', 'PHÒNG KHÁM', 'Trường', 'TRƯỜNG', 'Học viện', 'HỌC VIỆN', 'Bán lẻ', 'Nội bộ']
reg_sums = {"MB": 0, "MT": 0, "MN": 0}

for r in cur.fetchall():
    area = r[0]
    name = r[1] if r[1] else ''
    amt = r[2]
    
    is_hospital = False
    for kw in hospital_keywords:
        if kw in name:
            is_hospital = True
            break
    if is_hospital:
        reg_sums[area] += amt

for area, amt in reg_sums.items():
    print(f"  Area={area}, Amount={amt:,.0f}")
print(f"  Total ETC: {sum(reg_sums.values()):,.0f}")

conn.close()
