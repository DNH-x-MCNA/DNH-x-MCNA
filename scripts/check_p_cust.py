import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Query dms_khachhang
cur.execute('SELECT * FROM dms_khachhang WHERE "Code" = \'P000001\'')
print("dms_khachhang:", cur.fetchall())

# Query dmssx_khachhang
cur.execute('SELECT * FROM dmssx_khachhang WHERE "Code" = \'P000001\'')
print("dmssx_khachhang:", cur.fetchall())

# Query all customers to see if there is any other table
# Check if customer code starts with P
cur.execute('SELECT "Code", "Name" FROM dms_khachhang WHERE "Code" LIKE \'P%\'')
print("\ndms_khachhang starting with P:")
for r in cur.fetchall():
    print("  ", r)

cur.execute('SELECT "Code", "Name" FROM dmssx_khachhang WHERE "Code" LIKE \'P%\'')
print("\ndmssx_khachhang starting with P:")
for r in cur.fetchall():
    print("  ", r)

conn.close()
