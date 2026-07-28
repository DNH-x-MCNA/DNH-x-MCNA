import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Get distinct AreaCode and sum of Amount_Cus in fact_tonghopkhachhang for June 2026
cur.execute("""
    SELECT "AreaCode", SUM("Amount_Cus")
    FROM fact_tonghopkhachhang
    WHERE "SaveDate" = '2026-06-30T00:00:00'
    GROUP BY "AreaCode"
""")
print("=== fact_tonghopkhachhang Sales by AreaCode for June 2026 ===")
for r in cur.fetchall():
    print(f"  AreaCode: {r[0]}, Sum: {r[1]:,.0f}")

# Check if there is a channel column or if we can break it down by channel/employee
cur.execute("""
    SELECT "AreaCode2", SUM("Amount_Cus")
    FROM fact_tonghopkhachhang
    WHERE "SaveDate" = '2026-06-30T00:00:00'
    GROUP BY "AreaCode2"
""")
print("\n=== fact_tonghopkhachhang Sales by AreaCode2 for June 2026 ===")
for r in cur.fetchall():
    print(f"  AreaCode2: {r[0]}, Sum: {r[1]:,.0f}")

conn.close()
