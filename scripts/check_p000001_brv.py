import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

cur.execute("SELECT * FROM brv_khachhang WHERE \"Code\" = 'P000001'")
print(f"In brv_khachhang: {cur.fetchone()}")

# Check all columns of brv_khachhang
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'brv_khachhang'")
print(f"Columns: {[r[0] for r in cur.fetchall()]}")

conn.close()
