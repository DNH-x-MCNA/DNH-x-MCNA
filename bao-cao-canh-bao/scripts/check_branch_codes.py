import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Distinct warehouse, branch, subbranch, distributor in June 2026 ETC
cur.execute("""
    SELECT "BranchCode", "WarehouseCode", "SubBranchCode", "DistributorCode", SUM("TotalAmount"), COUNT(*)
    FROM brvsx_hoadonhdr
    WHERE "IsActive" = TRUE
      AND "DocDate"::date >= '2026-06-01' AND "DocDate"::date <= '2026-06-30'
    GROUP BY "BranchCode", "WarehouseCode", "SubBranchCode", "DistributorCode"
    ORDER BY SUM("TotalAmount") DESC
""")
print("=== Branch/Warehouse/SubBranch combinations in ETC ===")
for r in cur.fetchall():
    print(f"  Branch={r[0]}, WH={r[1]}, SubBranch={r[2]}, Dist={r[3]} | Sum={r[4]:,.0f}, Count={r[5]}")

conn.close()
