import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# 1. Inspect columns of vw_hoadon_otc
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'vw_hoadon_otc' ORDER BY ordinal_position")
print("=== vw_hoadon_otc columns ===")
for r in cur.fetchall():
    print(f"  {r[0]} ({r[1]})")

# 2. Inspect columns of vw_hoadon_etc
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'vw_hoadon_etc' ORDER BY ordinal_position")
print("\n=== vw_hoadon_etc columns ===")
for r in cur.fetchall():
    print(f"  {r[0]} ({r[1]})")

# 3. Get view definitions
cur.execute("SELECT pg_get_viewdef('vw_hoadon_otc')")
print("\n=== vw_hoadon_otc Definition ===")
print(cur.fetchone()[0])

cur.execute("SELECT pg_get_viewdef('vw_hoadon_etc')")
print("\n=== vw_hoadon_etc Definition ===")
print(cur.fetchone()[0])

conn.close()
