import sys
sys.stdout.reconfigure(encoding='utf-8')
import psycopg2

conn = psycopg2.connect('postgresql://postgres.jfinzudbkmzyfqhlfoor:Trieu10052004%40@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres')
cur = conn.cursor()

# 1. OTC with IsHC = False
print('=== OTC June 2026 with IsHC = False ===')
cur.execute("""
    SELECT SUM(h."TotalAmount")
    FROM brv_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    LEFT JOIN brv_trangthaihoadon e ON h."EInvoiceStatus" = e."EInvoiceStatusKey"
    WHERE h."IsActive" = TRUE
      AND h."IsHC" = FALSE
      AND (d."IsCancelled" IS NULL OR d."IsCancelled" = FALSE)
      AND (e."IsCancelled" IS NULL OR e."IsCancelled" = FALSE)
      AND h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
""")
print(f"  OTC: {cur.fetchone()[0]:,.0f}")

# 2. ETC with IsHC = False
# Wait, does brvsx_hoadonhdr have IsHC? Let's check!
# Wait, does brvsx_hoadonhdr have IsHC? Let's look at the columns printed earlier:
# brvsx_hoadonhdr columns: Id, BranchCode, Stt, DocCode, DocDate, DocNo, IsActive, CreatedAt, ModifiedAt, DMSId, DocStatus, EInvoiceStatus, CustomerCode, BizDocId_SO, TotalAmount, Description, WarehouseCode, SubBranchCode, SyncAt, DistributorCode.
# No, brvsx_hoadonhdr does NOT have IsHC column!
# Wait! Then how do we filter ETC?
# Let's check how to filter ETC or what could be the reason ETC June is 102.02B in DB but 29.40B in the slide!
# Wait! Let's check if there is an IsHC column in any other way, or if we need to filter by some other status or field for ETC.
# Let's print unique values of some fields in brvsx_hoadonhdr for June 2026.
print('\n=== ETC unique values of BranchCode for June 2026 ===')
cur.execute("""
    SELECT "BranchCode", COUNT(*), SUM("TotalAmount")
    FROM brvsx_hoadonhdr
    WHERE "DocDate"::date >= '2026-06-01' AND "DocDate"::date <= '2026-06-30'
    GROUP BY "BranchCode"
""")
for r in cur.fetchall():
    print(f"  BranchCode={r[0]}, count={r[1]}, TotalAmount={r[2]:,.0f}")

print('\n=== ETC unique values of DocStatus for June 2026 ===')
cur.execute("""
    SELECT h."DocStatus", d."IsCancelled", d."Post_SoCai", COUNT(*), SUM(h."TotalAmount")
    FROM brvsx_hoadonhdr h
    LEFT JOIN brv_trangthaiduyet d ON h."DocStatus" = d."DocStatusKey"
    WHERE h."DocDate"::date >= '2026-06-01' AND h."DocDate"::date <= '2026-06-30'
    GROUP BY h."DocStatus", d."IsCancelled", d."Post_SoCai"
""")
for r in cur.fetchall():
    print(f"  DocStatus={r[0]}, IsCancelled={r[1]}, PostSoCai={r[2]}, count={r[3]}, TotalAmount={r[4]:,.0f}")

conn.close()
