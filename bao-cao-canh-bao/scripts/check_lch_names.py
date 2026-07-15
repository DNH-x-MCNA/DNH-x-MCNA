import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Get distinct LCH_FK and some sample names
cur.execute('SELECT DISTINCT "LCH_FK" FROM dmssx_khachhang')
lch_list = [r[0] for r in cur.fetchall()]

for lch in lch_list:
    if lch is None:
        cur.execute('SELECT "Code", "Name" FROM dmssx_khachhang WHERE "LCH_FK" IS NULL LIMIT 5')
        print(f"\nLCH_FK = NULL (None):")
    else:
        cur.execute('SELECT "Code", "Name" FROM dmssx_khachhang WHERE "LCH_FK" = %s LIMIT 5', (lch,))
        print(f"\nLCH_FK = {lch}:")
    for r in cur.fetchall():
        print(f"  {r[0]} | {r[1]}")

conn.close()
