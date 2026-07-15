import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Get sum of month_sale_amount by area_code for kpi_summary
cur.execute("""
    SELECT area_code, SUM(month_sale_amount)
    FROM kpi_summary
    GROUP BY area_code
""")
print("=== kpi_summary month_sale_amount by area_code ===")
for r in cur.fetchall():
    print(f"  AreaCode: {r[0]}, Sum: {r[1]:,.0f}")

# Check if there is any employee role TP or QLV or TDV
cur.execute("""
    SELECT position_code, SUM(month_sale_amount)
    FROM kpi_summary
    GROUP BY position_code
""")
print("\n=== kpi_summary month_sale_amount by position ===")
for r in cur.fetchall():
    print(f"  Position: {r[0]}, Sum: {r[1]:,.0f}")

conn.close()
