import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

cur.execute("SELECT * FROM dms_khachhang WHERE \"Code\" = 'P000001'")
print(f"In dms_khachhang: {cur.fetchone()}")

cur.execute("SELECT * FROM dmssx_khachhang WHERE \"Code\" = 'P000001'")
print(f"In dmssx_khachhang: {cur.fetchone()}")

# Check if there are other customer tables
cur.execute("""
    SELECT table_name FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name LIKE '%khachhang%'
""")
print(f"Customer tables: {[r[0] for r in cur.fetchall()]}")

conn.close()
