import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# 1. Sum Amount9 from vw_hoadon_otc for June 2026 by AreaCode
print("=== vw_hoadon_otc June 2026 by AreaCode ===")
cur.execute("""
    SELECT t."AreaCode", SUM(o."Amount9")
    FROM vw_hoadon_otc o
    JOIN dim_tinhthanhpho t ON o."CityId" = t."CityId"
    WHERE o."DocDate"::date >= '2026-06-01' AND o."DocDate"::date <= '2026-06-30'
    GROUP BY t."AreaCode"
    ORDER BY t."AreaCode"
""")
for r in cur.fetchall():
    val = f"{r[1]:,.0f}" if r[1] is not None else "0"
    print(f"  AreaCode={r[0]}, Amount9={val}")

# Total OTC from view
cur.execute("""
    SELECT SUM("Amount9")
    FROM vw_hoadon_otc
    WHERE "DocDate"::date >= '2026-06-01' AND "DocDate"::date <= '2026-06-30'
""")
print(f"  Total OTC: {cur.fetchone()[0]:,.0f}")

# 2. Sum Amount9 from vw_hoadon_etc for June 2026 by AreaCode
# Wait, vw_hoadon_etc doesn't have CityId directly?
# Let's check columns: BranchCode, DistributorCode, Id, RowId, ItemCode, Unit, Quantity, UnitPrice, Amount9, TaxCode, TaxRate, Amount3, DiscountRate, Amount4, Reduce, CTKM, CreatedAt, ModifiedAt, SyncAt, DocDate, EmpDMSCode, EmpDMSCode2, CustomerCode, Stt, DocCode, DocNo, DMSId, ContractId, Description.
# No, it doesn't have CityId. We must join dmssx_khachhang and dim_tinhthanhpho.
print("\n=== vw_hoadon_etc June 2026 by AreaCode ===")
cur.execute("""
    SELECT t."AreaCode", SUM(o."Amount9")
    FROM vw_hoadon_etc o
    JOIN dmssx_khachhang k ON o."CustomerCode" = k."Code"
    JOIN dim_tinhthanhpho t ON k."CityId" = t."CityId"
    WHERE o."DocDate"::date >= '2026-06-01' AND o."DocDate"::date <= '2026-06-30'
    GROUP BY t."AreaCode"
    ORDER BY t."AreaCode"
""")
for r in cur.fetchall():
    val = f"{r[1]:,.0f}" if r[1] is not None else "0"
    print(f"  AreaCode={r[0]}, Amount9={val}")

# Total ETC from view
cur.execute("""
    SELECT SUM("Amount9")
    FROM vw_hoadon_etc
    WHERE "DocDate"::date >= '2026-06-01' AND "DocDate"::date <= '2026-06-30'
""")
print(f"  Total ETC: {cur.fetchone()[0]:,.0f}")

conn.close()
