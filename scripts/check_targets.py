import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Query dim_targetvungmien
cur.execute('SELECT * FROM dim_targetvungmien')
print("=== dim_targetvungmien ===")
for r in cur.fetchall():
    print(r)

# Query fact_kehoachtongetc
cur.execute('SELECT * FROM fact_kehoachtongetc')
print("\n=== fact_kehoachtongetc ===")
for r in cur.fetchall():
    # print columns
    print(r)

conn.close()
