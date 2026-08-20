# -*- coding: utf-8 -*-
"""Kiem chung nghi van 20/08/2026: chatbot bao brv_sanpham.group_code RONG 100% (402/402 san pham)
nen KHONG tra loi duoc cau "nhom san pham nao dong gop doanh thu lon nhat" (Q033 PRD_GROUP).

ETL (sync_warehouse.py:218) DANG keo dung cot GroupCode tu dbo.BRV_SanPham. Neu kho local rong,
chi co 2 kha nang - script nay phan biet dut khoat:
  (A) Ben Bravo cot GroupCode BAN THAN da rong  -> loi/thieu du lieu NGUON, phai bao DNH.
  (B) Ben Bravo co du lieu, kho local rong      -> loi DONG BO cua minh, phai sua ETL.

Va neu (A): tim xem nhom san pham that su nam o dau (bang/cot khac) de con duong sua.

Chay tren may 24 (can noi duoc SQL Server):
    cd C:\\dnh_chatbot
    python scripts\\debug_product_group_code.py
"""
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path(os.environ.get("DNH_BACKEND_DIR", ROOT / "backend"))
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

for env_path in (BACKEND / ".env", ROOT / ".env"):
    if env_path.exists():
        with io.open(env_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

import report_templates as rt


def main():
    print("=" * 90)
    print("1) KHO LOCAL (SQLite) - brv_sanpham.group_code")
    print("=" * 90)
    local = rt._q("""
        SELECT COUNT(*) tong,
               SUM(CASE WHEN group_code IS NULL OR TRIM(group_code)='' THEN 1 ELSE 0 END) rong,
               COUNT(DISTINCT group_code) so_nhom_khac_nhau
        FROM brv_sanpham
    """)[0]
    print(f"  Tong san pham: {local['tong']}")
    print(f"  So dong group_code RONG/NULL: {local['rong']}")
    print(f"  So nhom khac nhau (ke ca NULL): {local['so_nhom_khac_nhau']}")
    sample = rt._q("SELECT code, name, group_code FROM brv_sanpham LIMIT 5")
    for s in sample:
        print(f"    {s['code']} | group_code={s['group_code']!r}")

    print()
    print("=" * 90)
    print("2) BRAVO LIVE - dbo.BRV_SanPham.GroupCode (nguon that)")
    print("=" * 90)
    try:
        bravo = rt._q_bravo("""
            SELECT COUNT(*) AS Tong,
                   SUM(CASE WHEN GroupCode IS NULL OR LTRIM(RTRIM(GroupCode))='' THEN 1 ELSE 0 END) AS Rong,
                   COUNT(DISTINCT GroupCode) AS SoNhom
            FROM dbo.BRV_SanPham
        """)[0]
        print(f"  Tong san pham: {bravo['Tong']}")
        print(f"  So dong GroupCode RONG/NULL: {bravo['Rong']}")
        print(f"  So nhom khac nhau: {bravo['SoNhom']}")

        if bravo["Rong"] < bravo["Tong"]:
            print("\n  -> BEN BRAVO CO DU LIEU. Top 10 nhom:")
            top = rt._q_bravo("""
                SELECT TOP (10) GroupCode, COUNT(*) AS SoMa
                FROM dbo.BRV_SanPham
                WHERE GroupCode IS NOT NULL AND LTRIM(RTRIM(GroupCode))<>''
                GROUP BY GroupCode ORDER BY COUNT(*) DESC
            """)
            for t in top:
                print(f"    {t['GroupCode']}: {t['SoMa']} ma")
            print("\n  ==> KET LUAN: (B) LOI DONG BO cua minh - Bravo co, kho local rong.")
        else:
            print("\n  ==> KET LUAN: (A) NGUON BRAVO cung rong - khong phai loi dong bo.")
    except Exception as exc:
        print(f"  LOI khi truy van Bravo: {type(exc).__name__}: {exc}")
        return

    print()
    print("=" * 90)
    print("3) TIM NHOM SAN PHAM O CHO KHAC tren Bravo (neu cot GroupCode rong)")
    print("=" * 90)
    try:
        objs = rt._q_bravo("""
            SELECT TOP (20) t.name AS TableName, c.name AS ColumnName
            FROM sys.columns c JOIN sys.tables t ON t.object_id=c.object_id
            WHERE c.name LIKE '%Group%' OR c.name LIKE '%Nhom%'
            ORDER BY t.name, c.name
        """)
        if objs:
            for o in objs:
                print(f"    {o['TableName']}.{o['ColumnName']}")
        else:
            print("    (khong tim thay cot nao ten chua Group/Nhom)")
    except Exception as exc:
        print(f"  Khong liet ke duoc catalog: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
