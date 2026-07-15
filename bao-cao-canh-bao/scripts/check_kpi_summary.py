import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Check table structure
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'kpi_summary'")
print("=== kpi_summary Columns ===")
for r in cur.fetchall():
    print(f"  {r[0]} ({r[1]})")

# Print all rows for June 2026
cur.execute("""
    SELECT * FROM kpi_summary
    WHERE "SaveDate" = '2026-06-30T00:00:00'
""")
print("\n=== kpi_summary Rows for June 2026 ===")
rows = cur.fetchall()
for r in rows:
    print(r)

conn.close()
