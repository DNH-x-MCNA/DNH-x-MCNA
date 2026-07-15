import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

cur.execute("""
    SELECT "DocNo", "DocDate", "TotalAmount", "Description", "CustomerCode"
    FROM brvsx_hoadonhdr
    WHERE "CustomerCode" IN ('1001136', '1001679')
    LIMIT 5
""")
print("=== ETC Invoices ===")
for r in cur.fetchall():
    print(f"  DocNo={r[0]}, Date={r[1]}, Amount={r[2]:,.0f}, Desc={r[3]}, CustCode={r[4]}")

conn.close()
