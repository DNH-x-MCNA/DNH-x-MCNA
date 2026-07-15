import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'brv_hoadonhdr'")
print("=== brv_hoadonhdr Columns ===")
for r in cur.fetchall():
    print(f"  {r[0]} ({r[1]})")

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'brvsx_hoadonhdr'")
print("\n=== brvsx_hoadonhdr Columns ===")
for r in cur.fetchall():
    print(f"  {r[0]} ({r[1]})")

conn.close()
