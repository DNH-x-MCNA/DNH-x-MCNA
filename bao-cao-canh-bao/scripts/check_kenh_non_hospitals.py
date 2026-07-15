import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

codes = ['HNO04012', 'HNO03889', 'HNO03973', 'HDU00632']
cur.execute('SELECT "Code", "Name", "KenhBH" FROM dmssx_khachhang WHERE "Code" IN (%s, %s, %s, %s)', tuple(codes))
print("=== non-hospital channels in dmssx_khachhang ===")
for r in cur.fetchall():
    print(f"  Code={r[0]}, Name={r[1][:40]}, KenhBH={r[2]}")

conn.close()
