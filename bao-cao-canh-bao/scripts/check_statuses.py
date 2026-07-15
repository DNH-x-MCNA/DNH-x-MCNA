import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

print('=== brv_trangthaiduyet ===')
cur.execute('SELECT * FROM brv_trangthaiduyet')
for r in cur.fetchall():
    print(r)

print('\n=== brv_trangthaihoadon ===')
cur.execute('SELECT * FROM brv_trangthaihoadon')
for r in cur.fetchall():
    print(r)

conn.close()
