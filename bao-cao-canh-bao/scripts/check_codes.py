import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

for code in ['1001136', '1001679']:
    print(f"\n--- Checking code: {code} ---")
    cur.execute('SELECT "Code", "Name" FROM dms_khachhang WHERE "Code" = %s', (code,))
    print("  dms_khachhang:", cur.fetchall())
    
    cur.execute('SELECT "Code", "Name" FROM dmssx_khachhang WHERE "Code" = %s', (code,))
    print("  dmssx_khachhang:", cur.fetchall())

conn.close()
