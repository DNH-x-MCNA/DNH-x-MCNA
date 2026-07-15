import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

codes = ['HNO110847', 'HNO111081', 'VPH00005', 'NDI00013']
for c in codes:
    cur.execute("""
        SELECT k."Code", k."Name", SUM(h."TotalAmount")
        FROM brvsx_hoadonhdr h
        JOIN dmssx_khachhang k ON h."CustomerCode" = k."Code"
        WHERE h."CustomerCode" = %s
          AND h."IsActive" = TRUE
          AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
        GROUP BY k."Code", k."Name"
    """, (c,))
    r = cur.fetchone()
    if r:
        print(f"Code: {r[0]} | Name: {r[1]} | Amount: {r[2]:,.0f}")
    else:
        print(f"Code: {c} | No sales")

conn.close()
