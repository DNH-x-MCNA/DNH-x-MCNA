import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# Check negative values in brv_hoadonct
cur.execute("""
    SELECT COUNT(*), SUM("Amount9")
    FROM brv_hoadonct
    WHERE "Amount9" < 0
""")
cnt, amt = cur.fetchone()
print(f"Negative Amount9 in brv_hoadonct: {cnt} count, Sum: {amt or 0:,.0f}")

cur.execute("""
    SELECT COUNT(*), SUM("Quantity")
    FROM brv_hoadonct
    WHERE "Quantity" < 0
""")
cnt, qty = cur.fetchone()
print(f"Negative Quantity in brv_hoadonct: {cnt} count, Sum: {qty or 0:,.0f}")

conn.close()
