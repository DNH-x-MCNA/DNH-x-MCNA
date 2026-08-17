# -*- coding: utf-8 -*-
"""Bộ 90 câu hỏi nghiệp vụ khó và SQL ground truth độc lập cho chatbot DNH.

Mục tiêu:
  - Người kiểm thử hỏi chatbot bằng đúng câu trong CASES.
  - Chạy checker SQL tương ứng để lấy số đối chiếu từ nguồn đúng.
  - Không tự động phán PASS bằng so khớp câu chữ; người kiểm thử đối chiếu số, kỳ, phạm vi và cảnh báo.

Nguồn:
  - bravo: SQL Server NH_Report_TM, đọc trực tiếp dữ liệu thật.
  - bravo_sp: result set đọc trực tiếp từ stored procedure công nợ gốc DNH; runner
    materialize tạm trong RAM để chạy SELECT kiểm chứng, không dùng warehouse làm ground truth.

An toàn: SQL checker chỉ chấp nhận SELECT/WITH. Ngoại lệ duy nhất là runner nội bộ hard-code đúng
dbo.usp_DeptAccDueDate_GetData, đọc result set rồi rollback; model/người dùng không truyền được EXEC.

Ví dụ:
  python scripts/business_stress_suite.py --validate
  python scripts/business_stress_suite.py --list
  python scripts/business_stress_suite.py --show-sql Q061
  python scripts/business_stress_suite.py --execute --case Q061
  python scripts/business_stress_suite.py --execute --group "Công nợ" --scope-area MN
  python scripts/business_stress_suite.py --execute --smoke
  python scripts/business_stress_suite.py --execute --all --output results/stress-ground-truth.json
  python scripts/business_stress_suite.py --export-doc docs/chatbot_business_stress_test_90.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))


@dataclass(frozen=True)
class Checker:
    id: str
    database: str
    title: str
    sql: str
    notes: str = ""


@dataclass(frozen=True)
class BusinessCase:
    id: str
    group: str
    audience: str
    question: str
    checker_id: str
    pass_rule: str


def _sql(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.strip().splitlines())


CHECKERS: dict[str, Checker] = {}

DEBT_SP_DISPLAY = (
    "EXEC dbo.usp_DeptAccDueDate_GetData "
    "@_DocDate1=<dau_nam>, @_DocDate2=<as_of>, @_Period1=7, @_Period2=15, "
    "@_RepType=1, @_IsPrepaymentInclude=1"
)


def _checker(checker_id: str, database: str, title: str, sql: str, notes: str = "") -> None:
    CHECKERS[checker_id] = Checker(checker_id, database, title, _sql(sql), notes)


# ---------------------------------------------------------------------------
# Doanh thu, kênh, vùng và đối soát nguồn
# ---------------------------------------------------------------------------
_checker("REV_CHANNEL", "bravo", "Doanh thu và hóa đơn OTC/ETC tháng 07/2026", """
WITH Sales AS (
    SELECT 'OTC' Channel, Amount9, Stt FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT 'ETC', Amount9, Stt FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
)
SELECT Channel, SUM(Amount9) Revenue, COUNT(DISTINCT Stt) InvoiceCount
FROM Sales GROUP BY Channel
UNION ALL
SELECT 'TOTAL', SUM(Amount9), COUNT(DISTINCT CONCAT(Channel, '|', Stt)) FROM Sales
ORDER BY Channel
""")

_checker("REV_COMPARE", "bravo", "So sánh doanh thu 06/2026 và 07/2026", """
WITH Sales AS (
    SELECT DocDate, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-06-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT DocDate, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-06-01' AND DocDate < '2026-08-01'
), M AS (
    SELECT CONVERT(char(7), DocDate, 120) YearMonth, SUM(Amount9) Revenue
    FROM Sales GROUP BY CONVERT(char(7), DocDate, 120)
)
SELECT YearMonth, Revenue,
       Revenue - LAG(Revenue) OVER (ORDER BY YearMonth) Delta,
       100.0 * (Revenue - LAG(Revenue) OVER (ORDER BY YearMonth))
             / NULLIF(LAG(Revenue) OVER (ORDER BY YearMonth), 0) GrowthPct
FROM M ORDER BY YearMonth
""")

_checker("REV_DAILY", "bravo", "Doanh thu từng ngày tháng 07/2026", """
WITH Dates AS (
    SELECT CONVERT(date, '2026-07-01') DocDate
    UNION ALL
    SELECT DATEADD(day, 1, DocDate) FROM Dates WHERE DocDate < '2026-07-31'
), Sales AS (
    SELECT DocDate, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT DocDate, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
), Daily AS (
    SELECT DocDate, SUM(Amount9) Revenue FROM Sales GROUP BY DocDate
)
SELECT d.DocDate, ISNULL(s.Revenue, 0) Revenue
FROM Dates d LEFT JOIN Daily s ON s.DocDate=d.DocDate
ORDER BY d.DocDate
OPTION (MAXRECURSION 31)
""")

_checker("REV_WEEK", "bravo", "Doanh thu theo tuần trong tháng 07/2026", """
WITH Sales AS (
    SELECT DocDate, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT DocDate, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
)
SELECT DATEPART(ISO_WEEK, DocDate) IsoWeek, MIN(DocDate) FirstSaleDate,
       MAX(DocDate) LastSaleDate, SUM(Amount9) Revenue
FROM Sales GROUP BY DATEPART(ISO_WEEK, DocDate) ORDER BY IsoWeek
""")

_checker("REV_REGION", "bravo", "Doanh thu ba miền theo hồ sơ khách hàng", """
WITH PrefixMap AS (
    SELECT Prefix,AreaCode FROM (VALUES
      ('AGI','MN'),('BDI','MT'),('BDU','MN'),('BGI','MB'),('BKA','MB'),('BLI','MN'),
      ('BNI','MB'),('BPH','MN'),('BRV','MN'),('BTH','MN'),('BTR','MN'),('CBA','MB'),
      ('CMA','MN'),('CTH','MN'),('DBI','MB'),('DLA','MT'),('DNA','MT'),('DNI','MN'),
      ('DNO','MT'),('DTH','MN'),('GLA','MT'),('HBI','MB'),('HCM','MN'),('HDU','MB'),
      ('HGI','MB'),('HNA','MB'),('HNO','MB'),('HPH','MB'),('HTI','MB'),('HYE','MB'),
      ('KGI','MN'),('KHO','MT'),('KTU','MT'),('LAN','MN'),('LCA','MB'),('LCH','MB'),
      ('LDO','MT'),('LSO','MB'),('NAN','MB'),('NBI','MB'),('NDI','MB'),('NTH','MT'),
      ('PTH','MB'),('PYE','MT'),('QBI','MT'),('QNA','MT'),('QNG','MT'),('QNI','MB'),
      ('QTI','MT'),('SLA','MB'),('STR','MN'),('TBI','MB'),('TGI','MN'),('THO','MB'),
      ('TNG','MB'),('TNI','MN'),('TQU','MB'),('TTH','MT'),('TVI','MN'),('VLO','MN'),
      ('VPH','MB'),('YBA','MB')
    ) m(Prefix,AreaCode)
), Sales AS (
    SELECT 'OTC' Channel, CustomerCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT 'ETC', CustomerCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
), Located AS (
    SELECT s.Channel, s.Amount9,
           CASE WHEN tp.AreaCode IN ('MB','MB1','MB2') THEN 'MB'
                WHEN tp.AreaCode = 'MT' THEN 'MT'
                WHEN tp.AreaCode = 'MN' THEN 'MN'
                ELSE ISNULL(pm.AreaCode,'CHUA_XAC_DINH') END AreaCode
    FROM Sales s
    LEFT JOIN dbo.DMS_KhachHang kh ON kh.Code=s.CustomerCode
    LEFT JOIN dbo.DIM_TinhThanhPho tp ON tp.CityId=kh.CityId
    LEFT JOIN PrefixMap pm ON pm.Prefix=UPPER(LEFT(s.CustomerCode,3))
)
SELECT AreaCode, Channel, SUM(Amount9) Revenue
FROM Located GROUP BY AreaCode, Channel ORDER BY AreaCode, Channel
""", "Khách chưa có hồ sơ vùng phải hiện CHUA_XAC_DINH, không được âm thầm loại khỏi tổng.")

_checker("REV_INVOICE_STATS", "bravo", "Số hóa đơn và giá trị hóa đơn bình quân", """
WITH Invoice AS (
    SELECT 'OTC' Channel, Stt, SUM(Amount9) Revenue FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01' GROUP BY Stt
    UNION ALL
    SELECT 'ETC', Stt, SUM(Amount9) FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01' GROUP BY Stt
)
SELECT Channel, COUNT(*) InvoiceCount, SUM(Revenue) Revenue,
       AVG(CONVERT(decimal(28,2), Revenue)) AverageInvoiceValue,
       MAX(Revenue) LargestInvoiceValue
FROM Invoice GROUP BY Channel
""")

_checker("REV_RETURNS", "bravo", "Doanh thu điều chỉnh/hoàn âm", """
WITH Sales AS (
    SELECT 'OTC' Channel, DocDate, Stt, DocCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT 'ETC', DocDate, Stt, DocCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
)
SELECT Channel, COUNT(DISTINCT Stt) AffectedInvoices, SUM(Amount9) NegativeRevenue
FROM Sales WHERE Amount9 < 0 OR DocCode='HC' GROUP BY Channel
""")

_checker("REV_DISTRIBUTOR", "bravo", "Doanh thu theo nhà phân phối", """
WITH Sales AS (
    SELECT 'OTC' Channel, DistributorCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT 'ETC', DistributorCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
)
SELECT TOP (20) DistributorCode, Channel, SUM(Amount9) Revenue
FROM Sales GROUP BY DistributorCode, Channel ORDER BY SUM(Amount9) DESC
""")

_checker("REV_BRANCH", "bravo", "Doanh thu theo chi nhánh", """
WITH Sales AS (
    SELECT 'OTC' Channel, BranchCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
    UNION ALL
    SELECT 'ETC', BranchCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= '2026-07-01' AND DocDate < '2026-08-01'
)
SELECT BranchCode, Channel, SUM(Amount9) Revenue
FROM Sales GROUP BY BranchCode, Channel ORDER BY BranchCode, Channel
""")

_checker("REV_FRESHNESS", "bravo", "Ngày và thời điểm đồng bộ hóa đơn mới nhất", """
SELECT 'OTC' Channel, MAX(DocDate) MaxDocDate, MAX(SyncAt) MaxSyncAt, COUNT_BIG(*) [RowCount]
FROM dbo.vHoaDonTotal
UNION ALL
SELECT 'ETC', MAX(DocDate), MAX(SyncAt), COUNT_BIG(*) FROM dbo.vHoaDonETCTotal
""")

_checker("REV_RECONCILE", "bravo", "Đối soát view Total với view thường", """
SELECT 'OTC' Channel,
       (SELECT SUM(Amount9) FROM dbo.vHoaDonTotal WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01') TotalViewRevenue,
       (SELECT SUM(Amount9) FROM dbo.vHoaDon WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01') BaseViewRevenue
UNION ALL
SELECT 'ETC',
       (SELECT SUM(Amount9) FROM dbo.vHoaDonETCTotal WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'),
       (SELECT SUM(Amount9) FROM dbo.vHoaDonETC WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01')
""", "Doanh thu chuẩn dùng view Total vì view thường có thể thiếu dòng HC/điều chỉnh.")

# ---------------------------------------------------------------------------
# Khách hàng và sản phẩm
# ---------------------------------------------------------------------------
_checker("CUS_TOP", "bravo", "Top khách hàng theo doanh thu", """
WITH Sales AS (
    SELECT CustomerCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT CustomerCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
)
SELECT TOP (20) s.CustomerCode, MAX(kh.Name) CustomerName, SUM(s.Amount9) Revenue
FROM Sales s LEFT JOIN dbo.DMS_KhachHang kh ON kh.Code=s.CustomerCode
GROUP BY s.CustomerCode ORDER BY SUM(s.Amount9) DESC
""")

_checker("CUS_TREND", "bravo", "Doanh thu khách hàng giảm giữa hai kỳ ba tháng", """
WITH Sales AS (
    SELECT CustomerCode, DocDate, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-02-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT CustomerCode, DocDate, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-02-01' AND DocDate<'2026-08-01'
), R AS (
    SELECT CustomerCode,
      SUM(CASE WHEN DocDate>='2026-05-01' THEN Amount9 ELSE 0 END) RecentRevenue,
      SUM(CASE WHEN DocDate<'2026-05-01' THEN Amount9 ELSE 0 END) PriorRevenue
    FROM Sales GROUP BY CustomerCode
)
SELECT TOP (20) CustomerCode, RecentRevenue, PriorRevenue,
       100.0*(RecentRevenue-PriorRevenue)/NULLIF(PriorRevenue,0) ChangePct
FROM R WHERE RecentRevenue<PriorRevenue AND RecentRevenue>=100000000
ORDER BY ChangePct, RecentRevenue DESC
""")

_checker("CUS_STOPPED", "bravo", "Khách từng mua nhưng không mua trong 07/2026", """
WITH Sales AS (
    SELECT CustomerCode, DocDate, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-04-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT CustomerCode, DocDate, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-04-01' AND DocDate<'2026-08-01'
), R AS (
    SELECT CustomerCode,
      SUM(CASE WHEN DocDate<'2026-07-01' THEN Amount9 ELSE 0 END) PriorRevenue,
      SUM(CASE WHEN DocDate>='2026-07-01' THEN Amount9 ELSE 0 END) JulyRevenue,
      MAX(DocDate) LastPurchaseDate
    FROM Sales GROUP BY CustomerCode
)
SELECT TOP (30) CustomerCode, PriorRevenue, JulyRevenue, LastPurchaseDate
FROM R WHERE PriorRevenue>0 AND JulyRevenue=0 ORDER BY PriorRevenue DESC
""")

_checker("CUS_ACTIVITY", "bravo", "Khách mới/mua lại/hoạt động theo snapshot KPI", """
WITH Snap AS (
    SELECT MAX(SaveDate) SaveDate FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31'
)
SELECT IsNC, IsRO, IsAC, COUNT(DISTINCT CustomerCode) CustomerCount,
       SUM(Amount_CT) Revenue
FROM dbo.FACT_TongHopKhachHang
WHERE SaveDate=(SELECT SaveDate FROM Snap)
GROUP BY IsNC, IsRO, IsAC ORDER BY IsNC, IsRO, IsAC
""")

_checker("CUS_CONCENTRATION", "bravo", "Mức tập trung doanh thu vào top khách hàng", """
WITH Sales AS (
    SELECT CustomerCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT CustomerCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
), C AS (
    SELECT CustomerCode, SUM(Amount9) Revenue FROM Sales GROUP BY CustomerCode
), R AS (
    SELECT CustomerCode, Revenue, ROW_NUMBER() OVER (ORDER BY Revenue DESC) rn FROM C
)
SELECT SUM(Revenue) TotalRevenue,
       SUM(CASE WHEN rn<=10 THEN Revenue ELSE 0 END) Top10Revenue,
       100.0*SUM(CASE WHEN rn<=10 THEN Revenue ELSE 0 END)/NULLIF(SUM(Revenue),0) Top10SharePct
FROM R
""")

_checker("CUS_BASKET", "bravo", "Số SKU và giá trị đơn hàng theo khách", """
WITH Lines AS (
    SELECT CustomerCode, CONCAT('OTC|',Stt) OrderKey, ItemCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' AND UnitPrice>0
    UNION ALL
    SELECT CustomerCode, CONCAT('ETC|',Stt) OrderKey, ItemCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' AND UnitPrice>0
), Orders AS (
    SELECT CustomerCode, OrderKey, COUNT(DISTINCT ItemCode) SKUCount, SUM(Amount9) Revenue
    FROM Lines GROUP BY CustomerCode, OrderKey
)
SELECT TOP (20) CustomerCode, COUNT(*) OrderCount,
       AVG(CONVERT(decimal(18,2), SKUCount)) AvgSKUPerOrder,
       AVG(CONVERT(decimal(28,2), Revenue)) AvgOrderValue
FROM Orders GROUP BY CustomerCode HAVING COUNT(*)>=3 ORDER BY AvgOrderValue DESC
""")

_checker("PRD_TOP", "bravo", "Top sản phẩm theo doanh thu và số lượng bán thật", """
WITH Sales AS (
    SELECT ItemCode, Amount9, Quantity, UnitPrice FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT ItemCode, Amount9, Quantity, UnitPrice FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
)
SELECT TOP (20) s.ItemCode, MAX(p.Name) ProductName, SUM(s.Amount9) Revenue,
       SUM(CASE WHEN ISNULL(s.UnitPrice,0)>0 THEN s.Quantity ELSE 0 END) PaidQuantity
FROM Sales s LEFT JOIN dbo.BRV_SanPham p ON p.Code=s.ItemCode
GROUP BY s.ItemCode ORDER BY SUM(s.Amount9) DESC
""")

_checker("PRD_CHANNEL", "bravo", "Sản phẩm theo kênh OTC/ETC", """
WITH Sales AS (
    SELECT 'OTC' Channel, ItemCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT 'ETC', ItemCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
), R AS (
    SELECT Channel, ItemCode, SUM(Amount9) Revenue,
           ROW_NUMBER() OVER (PARTITION BY Channel ORDER BY SUM(Amount9) DESC) rn
    FROM Sales GROUP BY Channel, ItemCode
)
SELECT Channel, ItemCode, Revenue FROM R WHERE rn<=10 ORDER BY Channel, rn
""")

_checker("PRD_GROUP", "bravo", "Doanh thu theo nhóm sản phẩm", """
WITH Sales AS (
    SELECT ItemCode, CONVERT(varchar(50),GroupCode) GroupCode, Amount9 FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
    UNION ALL
    SELECT ItemCode, CONVERT(varchar(50),GroupCode) GroupCode, Amount9 FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
)
SELECT GroupCode, SUM(Amount9) Revenue, COUNT(DISTINCT ItemCode) ProductCount
FROM Sales GROUP BY GroupCode ORDER BY SUM(Amount9) DESC
""")

_checker("PRD_CROSSSELL", "bravo", "Cặp sản phẩm thường cùng xuất hiện", """
WITH Lines AS (
    SELECT DISTINCT CONCAT('OTC|',Stt) OrderKey, ItemCode FROM dbo.vHoaDonTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' AND UnitPrice>0
    UNION
    SELECT DISTINCT CONCAT('ETC|',Stt), ItemCode FROM dbo.vHoaDonETCTotal
    WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' AND UnitPrice>0
)
SELECT TOP (20) a.ItemCode ProductA, b.ItemCode ProductB, COUNT_BIG(*) OrdersTogether
FROM Lines a JOIN Lines b ON b.OrderKey=a.OrderKey AND b.ItemCode>a.ItemCode
GROUP BY a.ItemCode,b.ItemCode ORDER BY COUNT_BIG(*) DESC
""")

# ---------------------------------------------------------------------------
# KPI, cây tổ chức và dữ liệu nhân viên
# ---------------------------------------------------------------------------
_checker("KPI_EMPLOYEE", "bravo", "KPI nhân viên tại snapshot 31/07/2026", """
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31'),
Agg AS (
  SELECT EmployeeCode, MAX(ManagerCode) ManagerCode, SUM(Amount_CT) Actual,
         MAX(MonthSaleTarget) Target, COUNT(DISTINCT CustomerCode) Customers
  FROM dbo.FACT_TongHopKhachHang WHERE SaveDate=(SELECT d FROM Snap)
  GROUP BY EmployeeCode
)
SELECT a.EmployeeCode, n.Name EmployeeName, n.PositionCode, n.AreaCode, a.ManagerCode,
       a.Actual, a.Target, 100.0*a.Actual/NULLIF(a.Target,0) AchievementPct, a.Customers
FROM Agg a LEFT JOIN dbo.DIM_NhanVien n ON n.EmployeeCode=a.EmployeeCode
ORDER BY AchievementPct DESC
""")

_checker("KPI_THRESHOLDS", "bravo", "Ba mốc 100%, 80%, 65/70%", """
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31'),
E AS (
 SELECT EmployeeCode, PositionCode, AreaCode, MonthSaleAmount, MonthSaleTarget, MonthSalePercent_R,
        CASE WHEN PositionCode='TDV' THEN 0.65 ELSE 0.70 END BonusGate
 FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
)
SELECT PositionCode, AreaCode, COUNT(*) Employees,
 SUM(CASE WHEN MonthSalePercent_R>=1.00 THEN 1 ELSE 0 END) Reached100,
 SUM(CASE WHEN MonthSalePercent_R>=0.80 THEN 1 ELSE 0 END) ReachedKPI80,
 SUM(CASE WHEN MonthSalePercent_R>=BonusGate THEN 1 ELSE 0 END) ReachedGroupBonusGate
FROM E GROUP BY PositionCode, AreaCode ORDER BY PositionCode, AreaCode
""")

_checker("KPI_MANAGER", "bravo", "Tổng hợp KPI theo quản lý", """
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31'),
Emp AS (
 SELECT EmployeeCode, MAX(ManagerCode) ManagerCode, SUM(Amount_CT) Actual, MAX(MonthSaleTarget) Target
 FROM dbo.FACT_TongHopKhachHang WHERE SaveDate=(SELECT d FROM Snap) GROUP BY EmployeeCode
)
SELECT ManagerCode, COUNT(*) EmployeeCount, SUM(Actual) TeamActual, SUM(Target) TeamTarget,
       100.0*SUM(Actual)/NULLIF(SUM(Target),0) TeamAchievementPct
FROM Emp WHERE ManagerCode IS NOT NULL GROUP BY ManagerCode ORDER BY TeamAchievementPct DESC
""")

_checker("KPI_DAILY", "bravo", "Doanh số thực tế theo ngày và nhân viên", """
WITH Sales AS (
 SELECT DocDate, EmpDMSCode EmployeeDMS, Amount9 FROM dbo.vHoaDonTotal
 WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
 UNION ALL
 SELECT DocDate, EmpDMSCode, Amount9 FROM dbo.vHoaDonETCTotal
 WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01'
)
SELECT TOP (100) n.EmployeeCode, n.Name EmployeeName, s.DocDate, SUM(s.Amount9) DailyRevenue
FROM Sales s LEFT JOIN dbo.DIM_NhanVien n ON n.DMSId=s.EmployeeDMS
GROUP BY n.EmployeeCode,n.Name,s.DocDate ORDER BY SUM(s.Amount9) DESC
""")

_checker("KPI_TEAM_DAILY", "bravo", "Top ngày bán hàng theo từng đội quản lý", """
WITH Snap AS (
 SELECT MAX(SaveDate) d FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31'
), EmpMap AS (
 SELECT EmployeeCode,MAX(EmpDMSCode) EmpDMSCode,MAX(ManagerCode) ManagerCode
 FROM dbo.FACT_TongHopKhachHang WHERE SaveDate=(SELECT d FROM Snap)
 GROUP BY EmployeeCode
), Sales AS (
 SELECT DocDate,EmpDMSCode,SUM(Amount9) Revenue FROM dbo.vHoaDonTotal
 WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' GROUP BY DocDate,EmpDMSCode
 UNION ALL
 SELECT DocDate,EmpDMSCode,SUM(Amount9) Revenue FROM dbo.vHoaDonETCTotal
 WHERE DocDate>='2026-07-01' AND DocDate<'2026-08-01' GROUP BY DocDate,EmpDMSCode
), TeamDay AS (
 SELECT e.ManagerCode,s.DocDate,SUM(s.Revenue) Revenue
 FROM Sales s JOIN EmpMap e ON e.EmpDMSCode=s.EmpDMSCode
 WHERE NULLIF(e.ManagerCode,'') IS NOT NULL
 GROUP BY e.ManagerCode,s.DocDate
), Ranked AS (
 SELECT ManagerCode,DocDate,Revenue,
        ROW_NUMBER() OVER (PARTITION BY ManagerCode ORDER BY Revenue DESC,DocDate) RankInTeam
 FROM TeamDay
)
SELECT ManagerCode,DocDate,Revenue,RankInTeam
FROM Ranked WHERE RankInTeam<=10 ORDER BY ManagerCode,RankInTeam
""")

_checker("KPI_QUALITY", "bravo", "Nhân viên thiếu target hoặc thiếu quản lý", """
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31'),
Emp AS (
 SELECT EmployeeCode, MAX(ManagerCode) ManagerCode, MAX(MonthSaleTarget) Target,
        SUM(Amount_CT) Actual, COUNT(DISTINCT CustomerCode) Customers
 FROM dbo.FACT_TongHopKhachHang WHERE SaveDate=(SELECT d FROM Snap) GROUP BY EmployeeCode
)
SELECT e.EmployeeCode,n.Name,n.PositionCode,e.ManagerCode,e.Target,e.Actual,e.Customers
FROM Emp e LEFT JOIN dbo.DIM_NhanVien n ON n.EmployeeCode=e.EmployeeCode
WHERE ISNULL(e.Target,0)<=0 OR (n.PositionCode='TDV' AND NULLIF(e.ManagerCode,'') IS NULL)
ORDER BY n.PositionCode,e.EmployeeCode
""")

_checker("KPI_DUPLICATE", "bravo", "Nhân viên trùng/bóng và trùng snapshot", """
SELECT EmployeeCode, COUNT(*) DimRows,
       SUM(CASE WHEN IsDuplicate=1 THEN 1 ELSE 0 END) DuplicateFlags,
       SUM(CASE WHEN IsResigned=1 THEN 1 ELSE 0 END) ResignedFlags
FROM dbo.DIM_NhanVien GROUP BY EmployeeCode HAVING COUNT(*)>1 OR MAX(IsDuplicate)=1
ORDER BY COUNT(*) DESC, EmployeeCode
""")

_checker("KPI_CUSTOMER_FLAGS", "bravo", "Khách mới, mua lại, hoạt động theo nhân viên", """
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<='2026-07-31')
SELECT TOP (100) EmployeeCode, MAX(ManagerCode) ManagerCode,
       COUNT(DISTINCT CustomerCode) AssignedCustomers,
       COUNT(DISTINCT CASE WHEN IsNC=1 THEN CustomerCode END) NewCustomers,
       COUNT(DISTINCT CASE WHEN IsRO=1 THEN CustomerCode END) ReorderCustomers,
       COUNT(DISTINCT CASE WHEN IsAC=1 THEN CustomerCode END) ActiveCustomers,
       SUM(Amount_CT) Revenue
FROM dbo.FACT_TongHopKhachHang WHERE SaveDate=(SELECT d FROM Snap)
GROUP BY EmployeeCode ORDER BY Revenue DESC
""")

_checker("KPI_LAYER_RECON", "bravo", "Đối soát các tầng KPI không được cộng chồng", """
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT PositionCode, COUNT(*) Employees, SUM(MonthSaleAmount) SumMonthSaleAmount,
       SUM(MonthSaleTarget) SumMonthSaleTarget
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
GROUP BY PositionCode ORDER BY PositionCode
""", "Các tầng TP/QLV/TDV đều có roll-up; tuyệt đối không cộng toàn bảng để ra doanh thu công ty.")

# ---------------------------------------------------------------------------
# Công nợ: ground truth doc TRUC TIEP result set SP goc DNH, khong doc warehouse.db
# ---------------------------------------------------------------------------
_checker("DEBT_SUMMARY", "bravo_sp", "Tổng công nợ theo kênh", """
SELECT sales_channel, SUM(balance_end) balance_end, SUM(total_overdue) total_overdue,
       ROUND(100.0*SUM(total_overdue)/NULLIF(SUM(balance_end),0),1) overdue_pct,
       MAX(snapshot_at) snapshot_at
FROM fact_congno_khachhang GROUP BY sales_channel ORDER BY sales_channel
""", "Dữ liệu bảng tạm được nạp trực tiếp từ dbo.usp_DeptAccDueDate_GetData trong cùng lần chạy.")

_checker("DEBT_AREA", "bravo_sp", "Công nợ theo vùng", """
SELECT area_code, SUM(balance_end) balance_end, SUM(total_overdue) total_overdue,
       ROUND(100.0*SUM(total_overdue)/NULLIF(SUM(balance_end),0),1) overdue_pct
FROM fact_congno_khachhang GROUP BY area_code ORDER BY total_overdue DESC
""")

_checker("DEBT_TOP", "bravo_sp", "Top 30 khách hàng nợ quá hạn", """
SELECT customer_code, MAX(customer_name) customer_name, SUM(balance_end) balance_end,
       SUM(total_overdue) total_overdue,
       ROUND(100.0*SUM(total_overdue)/NULLIF(SUM(balance_end),0),1) overdue_pct
FROM fact_congno_khachhang GROUP BY customer_code
HAVING SUM(total_overdue)>0 ORDER BY total_overdue DESC LIMIT 30
""")

_checker("DEBT_AGING", "bravo_sp", "Cơ cấu tuổi nợ theo kênh", """
SELECT sales_channel, SUM(overdue_1_15) overdue_1_15,
       SUM(overdue_15_30) overdue_16_30, SUM(overdue_30_45) overdue_31_45,
       SUM(overdue_gt_45) overdue_gt_45,
       SUM(total_overdue) total_overdue
FROM fact_congno_khachhang GROUP BY sales_channel ORDER BY sales_channel
""")

_checker("DEBT_RISK", "bravo_sp", "Khách doanh thu lớn, nợ cao và sức mua giảm", """
WITH debt AS (
 SELECT customer_code, MAX(customer_name) customer_name, SUM(balance_end) balance_end,
        SUM(total_overdue) overdue, MAX(snapshot_at) snapshot_at
 FROM fact_congno_khachhang GROUP BY customer_code
)
SELECT r.customer_code,d.customer_name,r.recent_revenue,r.prior_revenue,r.change_pct,
       d.balance_end,d.overdue,d.snapshot_at
FROM sales_customer_period r JOIN debt d ON d.customer_code=r.customer_code
WHERE r.recent_revenue>=100000000 AND d.overdue>=50000000 AND r.recent_revenue<r.prior_revenue
ORDER BY d.overdue DESC,r.recent_revenue DESC LIMIT 30
""", "Doanh thu trong sales_customer_period cũng được tổng hợp trực tiếp từ hai view Total trên SQL Server.")

_checker("DEBT_SCOPE_AGING", "bravo_sp", "Tuổi nợ trong phạm vi vùng tài khoản", """
SELECT area_code,
       SUM(overdue_1_15) overdue_1_15,
       SUM(overdue_15_30) overdue_16_30,
       SUM(overdue_30_45) overdue_31_45,
       SUM(overdue_gt_45) overdue_gt_45,
       SUM(total_overdue) total_overdue
FROM fact_congno_khachhang
WHERE area_code=(SELECT area_code FROM test_scope LIMIT 1)
GROUP BY area_code
""", "Bắt buộc truyền --scope-area giống scope_value của tài khoản QLV; thiếu scope thì runner fail-closed.")

_checker("DEBT_RATIO_TOP", "bravo_sp", "Khách có tỷ lệ quá hạn trên dư nợ cao nhất", """
SELECT customer_code,MAX(customer_name) customer_name,
       SUM(balance_end) balance_end,SUM(total_overdue) total_overdue,
       ROUND(100.0*SUM(total_overdue)/NULLIF(SUM(balance_end),0),2) overdue_pct
FROM fact_congno_khachhang
GROUP BY customer_code
HAVING SUM(balance_end)>0 AND SUM(total_overdue)>0
ORDER BY overdue_pct DESC,total_overdue DESC LIMIT 30
""")

_checker("DEBT_DUAL_CHANNEL", "bravo_sp", "Khách phát sinh công nợ ở cả OTC và ETC", """
WITH customer_channel AS (
 SELECT customer_code,MAX(customer_name) customer_name,
        COUNT(DISTINCT sales_channel) channel_count,
        SUM(CASE WHEN sales_channel='OTC' THEN balance_end ELSE 0 END) otc_balance,
        SUM(CASE WHEN sales_channel='ETC' THEN balance_end ELSE 0 END) etc_balance,
        SUM(CASE WHEN sales_channel='OTC' THEN total_overdue ELSE 0 END) otc_overdue,
        SUM(CASE WHEN sales_channel='ETC' THEN total_overdue ELSE 0 END) etc_overdue
 FROM fact_congno_khachhang GROUP BY customer_code
)
SELECT COUNT(*) customer_count,SUM(otc_balance) otc_balance,SUM(etc_balance) etc_balance,
       SUM(otc_overdue) otc_overdue,SUM(etc_overdue) etc_overdue,
       SUM(otc_balance+etc_balance) total_balance,SUM(otc_overdue+etc_overdue) total_overdue
FROM customer_channel WHERE channel_count=2
""")

_checker("DEBT_SNAPSHOT_QUALITY", "bravo_sp", "Thời điểm và tính nhất quán snapshot nguồn", """
SELECT COUNT(*) row_count,MIN(snapshot_at) min_snapshot_at,MAX(snapshot_at) max_snapshot_at,
       COUNT(DISTINCT snapshot_at) distinct_snapshot_times
FROM fact_congno_khachhang
""", "snapshot_at là giờ runner thực thi trực tiếp SP, không phải timestamp lấy từ warehouse.")

_checker("DEBT_AGING_QUALITY", "bravo_sp", "Đối chiếu tổng nhóm tuổi với số quá hạn nguồn", """
SELECT COUNT(*) row_count,
       SUM(CASE WHEN ABS(total_overdue-(overdue_1_15+overdue_15_30+overdue_30_45+overdue_gt_45))>1
                THEN 1 ELSE 0 END) broken_aging_sum,
       SUM(CASE WHEN ABS(total_overdue-source_overdue_amount)>1 THEN 1 ELSE 0 END) source_mismatch_rows,
       SUM(total_overdue) bucket_total,SUM(source_overdue_amount) source_overdue_total
FROM fact_congno_khachhang
""")

_checker("DEBT_MISSING_DIMENSIONS", "bravo_sp", "Dòng công nợ thiếu mã khách/vùng hoặc class lạ", """
SELECT COUNT(*) row_count,
       SUM(CASE WHEN customer_code IS NULL OR customer_code='' THEN 1 ELSE 0 END) missing_customer,
       SUM(CASE WHEN area_code IS NULL OR area_code='' THEN 1 ELSE 0 END) missing_area,
       SUM(CASE WHEN source_class_code NOT IN ('TM','SX') THEN 1 ELSE 0 END) unknown_class
FROM fact_congno_khachhang
""")

_checker("DEBT_CONCENTRATION", "bravo_sp", "Tỷ trọng nợ quá hạn tập trung ở top 10 khách", """
WITH customer_debt AS (
 SELECT customer_code,SUM(total_overdue) total_overdue
 FROM fact_congno_khachhang GROUP BY customer_code
), ranked AS (
 SELECT customer_code,total_overdue,
        ROW_NUMBER() OVER (ORDER BY total_overdue DESC) rank_no
 FROM customer_debt WHERE total_overdue>0
)
SELECT SUM(total_overdue) company_overdue,
       SUM(CASE WHEN rank_no<=10 THEN total_overdue ELSE 0 END) top10_overdue,
       ROUND(100.0*SUM(CASE WHEN rank_no<=10 THEN total_overdue ELSE 0 END)
             /NULLIF(SUM(total_overdue),0),2) top10_share_pct
FROM ranked
""")

# ---------------------------------------------------------------------------
# Lương thưởng/KPI thu nhập
# ---------------------------------------------------------------------------
_checker("SALARY_DETAIL", "bravo", "Chi tiết thưởng và phụ cấp theo nhân viên", """
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT TOP (300) EmployeeCode,EmployeeName,PositionCode,AreaCode,ManagerCode,SaveDate,
       MonthSaleAmount,MonthSaleTarget,MonthSalePercent_R,
       DM1Amount,DM1Percent_R,DM2Amount,DM2Percent_R,DM3Amount,DM3Percent_R,DMBonus,TotalPoint,
       V15Bonus,V22Bonus,V25Bonus,ASOBonus,LunchAmount_R,TransportAmount_R,PhoneAmount_R
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
ORDER BY EmployeeCode
""")

_checker("SALARY_RANK", "bravo", "Xếp hạng tổng thưởng kinh doanh", """
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT TOP (30) EmployeeCode,EmployeeName,PositionCode,AreaCode,MonthSalePercent_R,
       DMBonus,V15Bonus,V22Bonus,V25Bonus,ASOBonus,
       ISNULL(DMBonus,0)+ISNULL(V15Bonus,0)+ISNULL(V22Bonus,0)+ISNULL(V25Bonus,0)+ISNULL(ASOBonus,0) TotalBonus,
       ISNULL(LunchAmount_R,0)+ISNULL(TransportAmount_R,0)+ISNULL(PhoneAmount_R,0) Allowance
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
ORDER BY TotalBonus DESC
""", "TotalBonus chưa gồm lương cơ bản.")

_checker("SALARY_PROGRESS", "bravo", "Thưởng V15/V22/V25 theo số đã chốt", """
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT TOP (300) EmployeeCode,EmployeeName,PositionCode,AreaCode,
       V15Date,V15Amount,V15Percent_R,V15Bonus,
       V22Date,V22Amount,V22Percent_R,V22Bonus,
       V25Date,V25Amount,V25Percent_R,V25Bonus
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
ORDER BY V25Bonus DESC,V22Bonus DESC,V15Bonus DESC
""")

_checker("SALARY_ASO", "bravo", "Thưởng ASO và điều kiện đã chốt", """
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT TOP (300) EmployeeCode,EmployeeName,PositionCode,AreaCode,ASOCalType,
       ActiveCusQuantity,ActiveCusTarget,ACPercent_R,ASOQuantity,ASOPercent_R,ASOBonus,
       PassCheckASOForASO,PassCheckSaleForASO,PassCheckASOBonus
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
ORDER BY ASOBonus DESC,ASOPercent_R DESC
""")

_checker("SALARY_ACHIEVEMENT", "bravo", "Số người có thưởng V15/V22/V25/ASO", """
WITH Snap AS (SELECT MAX(SaveDate) d FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<='2026-07-31')
SELECT PositionCode,AreaCode,COUNT(*) Employees,
       SUM(CASE WHEN V15Bonus>0 THEN 1 ELSE 0 END) V15Achieved,
       SUM(CASE WHEN V22Bonus>0 THEN 1 ELSE 0 END) V22Achieved,
       SUM(CASE WHEN V25Bonus>0 THEN 1 ELSE 0 END) V25Achieved,
       SUM(CASE WHEN ASOBonus>0 THEN 1 ELSE 0 END) ASOAchieved
FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate=(SELECT d FROM Snap)
GROUP BY PositionCode,AreaCode ORDER BY PositionCode,AreaCode
""")

_checker("SALARY_RULES", "bravo", "Bậc thưởng đang hiệu lực", """
SELECT TypeCode,AreaCode,PositionCode,Description,StartDate,EndDate,
       FromValue,ToValue,Earn1,Earn2,EarnMax,CheckASO,CheckTargetEmp,ASOCusCondType
FROM dbo.DIM_BacThuong
WHERE TypeCode IN ('V15','V22','V25','ASO')
  AND StartDate<='2026-07-01' AND (EndDate IS NULL OR EndDate>='2026-07-31')
ORDER BY TypeCode,AreaCode,PositionCode,BuildInOrder
""")

_checker("SALARY_V25_MISMATCH", "bravo", "V25 đạt bậc nhưng số đã lưu bằng 0", """
SELECT TOP (50) f.EmployeeCode,f.EmployeeName,f.AreaCode,f.PositionCode,f.SaveDate,
       f.V25Date,f.V25Amount,f.MonthSaleTarget,f.V25Percent_R,f.V25Bonus
FROM dbo.FACT_ThongKeTinhLuong f
WHERE f.SaveDate='2026-07-31' AND f.V25Percent_R>0.7 AND ISNULL(f.V25Bonus,0)=0
AND EXISTS (
 SELECT 1 FROM dbo.DIM_BacThuong b
 WHERE b.TypeCode='V25' AND b.AreaCode=f.AreaCode AND b.PositionCode=f.PositionCode
   AND b.StartDate<='2026-07-01' AND (b.EndDate IS NULL OR b.EndDate>='2026-07-31')
   AND ISNULL(b.Earn1,0)>0
   AND f.V25Percent_R>=ISNULL(b.FromValue,0)/100.0
   AND f.V25Percent_R<ISNULL(b.ToValue,3000)/100.0
)
ORDER BY f.V25Percent_R DESC
""")

_checker("SALARY_SNAPSHOTS", "bravo", "Snapshot lương đã chốt và dòng giữa kỳ", """
SELECT SaveDate,COUNT(*) Employees,
       SUM(CASE WHEN V25Percent_R IS NULL THEN 1 ELSE 0 END) MissingV25Percent,
       SUM(CASE WHEN MonthSaleTarget<=0 OR MonthSaleTarget IS NULL THEN 1 ELSE 0 END) MissingTarget
FROM dbo.FACT_ThongKeTinhLuong
WHERE SaveDate>='2026-06-01' AND SaveDate<'2026-09-01'
GROUP BY SaveDate ORDER BY SaveDate
""")

_checker("SALARY_LCB_SCHEMA", "bravo", "Kiểm tra có/không dữ liệu lương cơ bản", """
SELECT c.name ColumnName,t.name DataType
FROM sys.columns c JOIN sys.types t ON t.user_type_id=c.user_type_id
WHERE c.object_id=OBJECT_ID('dbo.FACT_ThongKeTinhLuong')
  AND (c.name LIKE '%Luong%' OR c.name LIKE '%Salary%' OR c.name LIKE '%Level%')
ORDER BY c.column_id
""", "Không được gọi tổng thưởng + phụ cấp là tổng thu nhập nếu chưa có mapping Level -> LCB.")

# ---------------------------------------------------------------------------
# Chương trình khuyến mãi: tuyệt đối không group cột CTKM ghi chú trên hóa đơn
# ---------------------------------------------------------------------------
_checker("PROMO_COVERAGE", "bravo", "Mức phủ liên kết đơn hàng–CTKM", """
SELECT MIN(h.DocDate) FirstLinkedOrderDate,MAX(h.DocDate) LastLinkedOrderDate,
       COUNT_BIG(*) LinkRows,COUNT(DISTINCT x.OrderId) LinkedOrders,
       COUNT(DISTINCT x.ProgId) Programs,MAX(x.SyncAt) LastLinkSyncAt
FROM dbo.DMS_DonHangCTKM x LEFT JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
""")

_checker("PROMO_EFFECT", "bravo", "Hiệu quả CTKM tháng 12/2025", """
WITH ProgramOrders AS (
 SELECT x.ProgId,x.OrderId,MAX(h.CustomerCode) CustomerCode
 FROM dbo.DMS_DonHangHdr h JOIN dbo.DMS_DonHangCTKM x ON x.OrderId=h.Id
 WHERE h.DocDate>='2025-12-01' AND h.DocDate<'2026-01-01'
 GROUP BY x.ProgId,x.OrderId
), InvoiceByOrder AS (
 SELECT TRY_CONVERT(int,DMSId) OrderId,SUM(Amount9) Revenue
 FROM dbo.vHoaDonTotal
 WHERE DocDate>='2025-12-01' AND DocDate<'2026-01-01' AND TRY_CONVERT(int,DMSId) IS NOT NULL
 GROUP BY TRY_CONVERT(int,DMSId)
)
SELECT p.Id ProgramId,p.Code ProgramCode,p.Name ProgramName,
       COUNT_BIG(*) Orders,COUNT(DISTINCT po.CustomerCode) Customers,
       SUM(ISNULL(i.Revenue,0)) AssociatedRevenue,
       SUM(CASE WHEN i.OrderId IS NULL THEN 1 ELSE 0 END) OrdersWithoutInvoice
FROM ProgramOrders po JOIN dbo.DMS_CTKM p ON p.Id=po.ProgId
LEFT JOIN InvoiceByOrder i ON i.OrderId=po.OrderId
GROUP BY p.Id,p.Code,p.Name ORDER BY AssociatedRevenue DESC
""", "AssociatedRevenue không cộng ngang giữa các CTKM vì một đơn có thể gắn nhiều chương trình.")

_checker("PROMO_CUSTOMERS", "bravo", "Khách hàng tham gia từng CTKM", """
SELECT TOP (100) p.Code ProgramCode,p.Name ProgramName,h.CustomerCode,
       COUNT(DISTINCT x.OrderId) Orders
FROM dbo.DMS_DonHangCTKM x JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
JOIN dbo.DMS_CTKM p ON p.Id=x.ProgId
WHERE h.DocDate>='2025-12-01' AND h.DocDate<'2026-01-01'
GROUP BY p.Code,p.Name,h.CustomerCode ORDER BY Orders DESC
""")

_checker("PROMO_PRODUCTS", "bravo", "Sản phẩm điều kiện và hàng tặng CTKM", """
WITH Gifts AS (
 SELECT ProgId,COUNT(DISTINCT NULLIF(ItemCode,'')) GiftProducts,
        SUM(CONVERT(bigint,ISNULL(SlotQuantity,0))) GiftSlots
 FROM dbo.DMS_DonHangCTKM GROUP BY ProgId
), Configured AS (
 SELECT t.ProgId,COUNT(DISTINCT NULLIF(d.ItemId,'')) ConfiguredProducts
 FROM dbo.DMS_CTKMOnTop1 t JOIN dbo.DMS_DKKMCt d ON d.CondId=t.CondId GROUP BY t.ProgId
)
SELECT p.Code,p.Name,ISNULL(c.ConfiguredProducts,0) ConfiguredProducts,
       ISNULL(g.GiftProducts,0) GiftProducts,ISNULL(g.GiftSlots,0) GiftSlots
FROM dbo.DMS_CTKM p LEFT JOIN Gifts g ON g.ProgId=p.Id LEFT JOIN Configured c ON c.ProgId=p.Id
ORDER BY GiftSlots DESC
""")

_checker("PROMO_OVERLAP", "bravo", "Đơn hàng dùng nhiều CTKM", """
SELECT TOP (50) x.OrderId,h.DocDate,h.CustomerCode,COUNT(DISTINCT x.ProgId) ProgramCount,
       STRING_AGG(CONVERT(varchar(max),p.Code),', ') ProgramCodes
FROM dbo.DMS_DonHangCTKM x JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
JOIN dbo.DMS_CTKM p ON p.Id=x.ProgId
WHERE h.DocDate>='2025-12-01' AND h.DocDate<'2026-01-01'
GROUP BY x.OrderId,h.DocDate,h.CustomerCode HAVING COUNT(DISTINCT x.ProgId)>1
ORDER BY ProgramCount DESC
""")

_checker("PROMO_QUALITY", "bravo", "Chất lượng liên kết CTKM", """
SELECT COUNT_BIG(*) LinkRows,
       SUM(CASE WHEN h.Id IS NULL THEN 1 ELSE 0 END) MissingOrder,
       SUM(CASE WHEN p.Id IS NULL THEN 1 ELSE 0 END) MissingProgram,
       COUNT(DISTINCT CASE WHEN h.Id IS NOT NULL AND p.Id IS NOT NULL THEN x.Id END) ValidLinks,
       MAX(h.DocDate) LastLinkedOrderDate
FROM dbo.DMS_DonHangCTKM x LEFT JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
LEFT JOIN dbo.DMS_CTKM p ON p.Id=x.ProgId
""")

# ---------------------------------------------------------------------------
# Tồn kho, đơn hàng và độ đầy đủ dữ liệu
# ---------------------------------------------------------------------------
_checker("INV_SUMMARY", "bravo", "Tồn kho theo chi nhánh", """
SELECT k.BranchCode,COUNT(DISTINCT t.ItemId) ProductCount,
       SUM(t.Quantity) Quantity,SUM(t.Amount) InventoryValue
FROM dbo.BRV_TonKhoDK t LEFT JOIN dbo.BRV_Kho k ON k.Id=t.WarehouseId
WHERE t.IsActive=1 GROUP BY k.BranchCode ORDER BY k.BranchCode
""")

_checker("INV_NEGATIVE", "bravo", "Tồn kho âm hoặc giá trị bất thường", """
SELECT TOP (100) k.BranchCode,k.Code WarehouseCode,t.ItemId,p.Code ItemCode,p.Name ProductName,
       t.Quantity,t.Amount
FROM dbo.BRV_TonKhoDK t LEFT JOIN dbo.BRV_Kho k ON k.Id=t.WarehouseId
LEFT JOIN dbo.BRV_SanPham p ON p.Id=t.ItemId
WHERE t.IsActive=1 AND (t.Quantity<0 OR t.Amount<0)
ORDER BY ABS(t.Amount) DESC
""")

_checker("ORDER_LAG", "bravo", "Độ trễ tạo đơn DMS đến hóa đơn", """
SELECT TOP (100) h.Id OrderId,h.DocDate OrderDate,MIN(v.DocDate) InvoiceDate,h.CustomerCode,
       DATEDIFF(day,h.DocDate,MIN(v.DocDate)) LagDays,SUM(v.Amount9) Revenue
FROM dbo.DMS_DonHangHdr h JOIN dbo.vHoaDonTotal v ON TRY_CONVERT(int,v.DMSId)=h.Id
WHERE h.DocDate>='2026-07-01' AND h.DocDate<'2026-08-01'
GROUP BY h.Id,h.DocDate,h.CustomerCode
HAVING ABS(DATEDIFF(day,h.DocDate,MIN(v.DocDate)))>=2
ORDER BY ABS(DATEDIFF(day,h.DocDate,MIN(v.DocDate))) DESC
""")

_checker("ORDER_NO_INVOICE", "bravo", "Đơn DMS chưa tìm thấy hóa đơn", """
SELECT TOP (100) h.Id OrderId,h.DocDate,h.CustomerCode,h.StatusId,h.StatusDescription,h.IsSync,h.SKUQuantity
FROM dbo.DMS_DonHangHdr h
WHERE h.DocDate>='2026-07-01' AND h.DocDate<'2026-08-01'
AND NOT EXISTS (SELECT 1 FROM dbo.vHoaDonTotal v WHERE TRY_CONVERT(int,v.DMSId)=h.Id)
ORDER BY h.DocDate DESC,h.Id DESC
""")

_checker("SOURCE_FRESHNESS", "bravo", "Mốc dữ liệu mới nhất của các nguồn chính", """
SELECT 'vHoaDonTotal' SourceName,MAX(DocDate) BusinessDate,MAX(SyncAt) SyncAt FROM dbo.vHoaDonTotal
UNION ALL SELECT 'vHoaDonETCTotal',MAX(DocDate),MAX(SyncAt) FROM dbo.vHoaDonETCTotal
UNION ALL SELECT 'FACT_TongHopKhachHang',MAX(SaveDate),MAX(CreatedAt) FROM dbo.FACT_TongHopKhachHang
UNION ALL SELECT 'FACT_ThongKeTinhLuong',MAX(SaveDate),MAX(CreatedAt) FROM dbo.FACT_ThongKeTinhLuong
UNION ALL SELECT 'DMS_DonHangCTKM',MAX(h.DocDate),MAX(x.SyncAt)
FROM dbo.DMS_DonHangCTKM x LEFT JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
""")


def _case(number: int, group: str, audience: str, question: str,
          checker_id: str, pass_rule: str) -> BusinessCase:
    return BusinessCase(f"Q{number:03d}", group, audience, question, checker_id, pass_rule)


CASES = [
    # 01-12: doanh thu/kênh
    _case(1,"Doanh thu","c_level","Tháng 7/2026 doanh thu thực thuần của OTC, ETC và toàn công ty là bao nhiêu; mỗi kênh có bao nhiêu hóa đơn?","REV_CHANNEL","Khớp doanh thu và số hóa đơn từng kênh; tổng bằng OTC + ETC."),
    _case(2,"Doanh thu","c_level","So với tháng 6/2026, doanh thu tháng 7/2026 tăng hay giảm bao nhiêu tiền và bao nhiêu phần trăm?","REV_COMPARE","Khớp hai kỳ trọn tháng và công thức chênh lệch."),
    _case(3,"Doanh thu","manager","Ngày nào trong tháng 7 có doanh thu cao nhất và thấp nhất; chênh nhau bao nhiêu?","REV_DAILY","Lấy cực trị từ đúng doanh thu từng ngày."),
    _case(4,"Doanh thu","tp","Tuần nào trong tháng 7 đóng góp doanh thu lớn nhất và chiếm bao nhiêu phần trăm tháng?","REV_WEEK","Tổng các tuần khớp doanh thu tháng, nêu rõ tuần cắt qua đầu/cuối tháng."),
    _case(5,"Doanh thu","c_level","Cơ cấu doanh thu tháng 7 theo ba miền và theo OTC/ETC thế nào?","REV_REGION","Không làm mất khách chưa xác định vùng; tổng vùng khớp tổng công ty."),
    _case(6,"Doanh thu","manager","Miền nào phụ thuộc ETC nhiều nhất trong tháng 7?","REV_REGION","Tỷ trọng ETC/tổng miền tính từ cùng một kỳ."),
    _case(7,"Doanh thu","c_level","Giá trị hóa đơn bình quân và hóa đơn lớn nhất tháng 7 của từng kênh là bao nhiêu?","REV_INVOICE_STATS","Tính ở cấp hóa đơn, không lấy trung bình dòng hàng."),
    _case(8,"Doanh thu","manager","Các hóa đơn điều chỉnh hoặc hoàn trong tháng 7 làm giảm doanh thu từng kênh bao nhiêu?","REV_RETURNS","Bao gồm Amount9 âm/DocCode HC; không dùng view bỏ mất điều chỉnh."),
    _case(9,"Doanh thu","tp","Top 20 nhà phân phối theo doanh thu tháng 7, tách theo kênh?","REV_DISTRIBUTOR","Thứ hạng và doanh thu khớp SQL."),
    _case(10,"Doanh thu","c_level","Doanh thu tháng 7 theo từng chi nhánh và kênh; chi nhánh nào lớn nhất?","REV_BRANCH","Không nhầm chi nhánh với vùng khách hàng."),
    _case(11,"Doanh thu","manager","Dữ liệu hóa đơn OTC và ETC mới nhất đang đến ngày nào, đồng bộ lúc nào?","REV_FRESHNESS","Phải nêu riêng business date và sync time."),
    _case(12,"Doanh thu","c_level","Đối soát doanh thu tháng 7 giữa view tổng và view thường: lệch bao nhiêu và nên tin nguồn nào?","REV_RECONCILE","Chọn view Total làm nguồn chuẩn và giải thích dòng HC/điều chỉnh."),

    # 13-24: vùng/đội/cây tổ chức
    _case(13,"Đội ngũ","tp","Xếp hạng toàn bộ nhân viên theo tỷ lệ hoàn thành chỉ tiêu tháng 7, kèm doanh số, target và số khách phụ trách.","KPI_EMPLOYEE","Không cộng trùng target theo khách hàng."),
    _case(14,"Đội ngũ","tp","Đội của quản lý nào có tỷ lệ hoàn thành tháng 7 cao nhất?","KPI_MANAGER","Gộp đúng nhân viên theo ManagerCode."),
    _case(15,"Đội ngũ","qlv","Trong đội tôi, ai đạt 100% chỉ tiêu, ai đạt KPI 80%, ai mới chỉ qua cổng thưởng nhóm hàng?","KPI_THRESHOLDS","Phân biệt rõ ba mốc 100/80/65-70."),
    _case(16,"Đội ngũ","manager","Bao nhiêu TDV chưa có quản lý trực tiếp trong dữ liệu tháng 7?","KPI_QUALITY","Không trả doanh thu 0 thay cho lỗi thiếu ManagerCode."),
    _case(17,"Đội ngũ","manager","Những nhân viên nào có doanh số nhưng không có chỉ tiêu tháng 7?","KPI_QUALITY","Liệt kê target rỗng/0 và doanh số thực tế."),
    _case(18,"Đội ngũ","qlv","Top 10 ngày bán hàng tốt nhất của đội trong tháng 7 là những ngày nào?","KPI_TEAM_DAILY","Gộp đúng nhân viên vào ManagerCode qua DMSId rồi mới xếp hạng theo ngày."),
    _case(19,"Đội ngũ","tp","So sánh số khách mới, khách mua lại và khách hoạt động của từng nhân viên cuối tháng 7.","KPI_CUSTOMER_FLAGS","Dùng trực tiếp IsNC/IsRO/IsAC, không suy diễn."),
    _case(20,"Đội ngũ","manager","Nhân viên nào đang xuất hiện trùng hoặc là bản ghi bóng trong danh mục nhân sự?","KPI_DUPLICATE","Nêu IsDuplicate/IsResigned, không đưa bản ghi bóng vào xếp hạng."),
    _case(21,"Đội ngũ","c_level","Vì sao không được cộng doanh số tất cả dòng TP, QLV, TDV trong bảng lương để ra doanh thu công ty?","KPI_LAYER_RECON","Chỉ ra các tầng roll-up chồng nhau bằng số thật."),
    _case(22,"Đội ngũ","tp","Tổng target và doanh số của các đội dưới quyền tháng 7 là bao nhiêu, đội nào dưới 80%?","KPI_MANAGER","Target đội không bị nhân theo số khách."),
    _case(23,"Đội ngũ","qlv","Trong đội tôi ai có nhiều khách phụ trách nhưng tỷ lệ hoàn thành thấp nhất?","KPI_EMPLOYEE","So sánh đồng thời customer count và achievement."),
    _case(24,"Đội ngũ","manager","Có trường hợp một nhân viên vừa thiếu target vừa thiếu quản lý không?","KPI_QUALITY","Trả đúng danh sách giao của hai điều kiện."),

    # 25-36: khách hàng/sản phẩm
    _case(25,"Khách hàng & sản phẩm","manager","Top 20 khách hàng doanh thu lớn nhất tháng 7 là ai?","CUS_TOP","Khớp mã, tên và doanh thu; OTC+ETC chỉ cộng một lần."),
    _case(26,"Khách hàng & sản phẩm","tp","Khách hàng doanh thu ít nhất 100 triệu trong 3 tháng gần đây nhưng giảm mạnh so với 3 tháng trước là ai?","CUS_TREND","So hai giai đoạn cùng độ dài 05-07 và 02-04."),
    _case(27,"Khách hàng & sản phẩm","qlv","Khách từng mua trong quý II nhưng không phát sinh mua hàng tháng 7 là ai?","CUS_STOPPED","Không gọi đây là dự báo rời bỏ; chỉ mô tả dữ liệu lịch sử."),
    _case(28,"Khách hàng & sản phẩm","manager","Cuối tháng 7 có bao nhiêu khách mới, mua lại và hoạt động; doanh thu từng nhóm?","CUS_ACTIVITY","Dùng cờ KPI gốc, không suy ra IsRO từ IsNC."),
    _case(29,"Khách hàng & sản phẩm","c_level","Top 10 khách hàng chiếm bao nhiêu phần trăm doanh thu toàn công ty tháng 7?","CUS_CONCENTRATION","Tử và mẫu cùng kỳ/cùng nguồn."),
    _case(30,"Khách hàng & sản phẩm","qlv","Khách nào có giá trị đơn bình quân cao nhưng số SKU mỗi đơn thấp?","CUS_BASKET","Tính theo cấp đơn, chỉ hàng bán thật UnitPrice>0."),
    _case(31,"Khách hàng & sản phẩm","manager","Top 20 sản phẩm tháng 7 theo doanh thu và số lượng bán thật?","PRD_TOP","Loại số lượng hàng giá 0 khỏi PaidQuantity."),
    _case(32,"Khách hàng & sản phẩm","manager","Top 10 sản phẩm OTC và top 10 ETC có khác nhau thế nào?","PRD_CHANNEL","Xếp hạng riêng từng kênh."),
    _case(33,"Khách hàng & sản phẩm","c_level","Nhóm sản phẩm nào đóng góp doanh thu lớn nhất và có bao nhiêu mã hàng bán ra?","PRD_GROUP","Khớp GroupCode, doanh thu và số mã."),
    _case(34,"Khách hàng & sản phẩm","manager","Những cặp sản phẩm nào thường được mua cùng một đơn nhất trong tháng 7?","PRD_CROSSSELL","Ghép theo OrderKey có cả kênh, không tạo cặp A-A hoặc đếm đôi A-B/B-A."),
    _case(35,"Khách hàng & sản phẩm","qlv","Trong top khách tháng 7, khách nào không có tên trong danh mục DMS?","CUS_TOP","Giữ mã khách mồ côi và hiển thị thiếu tên thay vì loại khỏi doanh thu."),
    _case(36,"Khách hàng & sản phẩm","manager","Sản phẩm nào có doanh thu cao nhưng số lượng bán thật thấp, cho thấy giá trị mỗi đơn vị cao?","PRD_TOP","So doanh thu với PaidQuantity, không tính hàng tặng."),

    # 37-48: công nợ/rủi ro
    _case(37,"Công nợ","c_level","Tổng dư nợ, nợ quá hạn và tỷ lệ quá hạn hiện tại của OTC và ETC?","DEBT_SUMMARY","Dùng snapshot SP gốc DNH; nêu thời điểm snapshot."),
    _case(38,"Công nợ","manager","Miền nào có tổng nợ quá hạn cao nhất và tỷ lệ quá hạn bao nhiêu?","DEBT_AREA","Không cộng tỷ lệ phần trăm trực tiếp."),
    _case(39,"Công nợ","manager","Top 30 khách hàng nợ quá hạn lớn nhất hiện tại?","DEBT_TOP","Gộp mọi dòng/kênh theo customer_code trước khi xếp hạng."),
    _case(40,"Công nợ","c_level","Cơ cấu nợ quá hạn 1-15, 16-30, 31-45 và trên 45 ngày theo từng kênh?","DEBT_AGING","Tổng bốn bucket khớp total_overdue."),
    _case(41,"Công nợ","manager","Tìm khách đồng thời doanh thu lớn, nợ quá hạn cao và sức mua giảm.","DEBT_RISK","Một truy vấn tổng hợp; kỳ 05-07 so 02-04, ngưỡng 100m/50m."),
    _case(42,"Công nợ","qlv","Khách nợ quá hạn trong phạm vi của tôi đang nằm chủ yếu ở nhóm tuổi nào?","DEBT_SCOPE_AGING","Khi test phải truyền --scope-area đúng scope_value của tài khoản QLV; thiếu scope thì fail-closed."),
    _case(43,"Công nợ","manager","Khách nào có tỷ lệ nợ quá hạn trên dư nợ cao nhất?","DEBT_RATIO_TOP","Không chia cho 0; phân biệt số tuyệt đối với tỷ lệ."),
    _case(44,"Công nợ","c_level","Có bao nhiêu khách đang có dư nợ ở cả OTC và ETC; tổng nợ của họ thế nào?","DEBT_DUAL_CHANNEL","Gộp theo mã khách và trả riêng dư nợ/quá hạn OTC, ETC."),
    _case(45,"Công nợ","manager","Snapshot công nợ được cập nhật lúc nào; có dấu hiệu cũ hoặc lệch thời gian giữa các dòng không?","DEBT_SNAPSHOT_QUALITY","Mốc nguồn là thời điểm SP được thực thi; mọi dòng phải cùng một mốc."),
    _case(46,"Công nợ","manager","Có dòng công nợ nào tổng bốn nhóm tuổi không bằng tổng quá hạn không?","DEBT_AGING_QUALITY","Đối chiếu cả tổng bốn bucket và OverDueAmount do SP trả về."),
    _case(47,"Công nợ","manager","Có bao nhiêu dòng công nợ thiếu mã khách hoặc thiếu vùng?","DEBT_MISSING_DIMENSIONS","Nêu số thiếu và ClassCode lạ, không âm thầm bỏ dòng."),
    _case(48,"Công nợ","c_level","Nếu tổng nợ quá hạn cao nhưng tập trung ở vài khách, top 10 chiếm bao nhiêu?","DEBT_CONCENTRATION","Tính top 10 sau khi gộp khách và chia cho tổng nợ quá hạn toàn nguồn."),

    # 49-62: KPI
    _case(49,"KPI","c_level","Toàn công ty tháng 7 có bao nhiêu người đạt đủ 100% chỉ tiêu?","KPI_THRESHOLDS","Dùng mốc 100%, không gọi 65/70 hoặc 80 là đạt chỉ tiêu."),
    _case(50,"KPI","c_level","Bao nhiêu người đạt KPI 80% nhưng chưa đạt đủ chỉ tiêu 100%?","KPI_THRESHOLDS","Lấy giao [80%,100%)."),
    _case(51,"KPI","manager","Bao nhiêu TDV đã qua cổng thưởng nhóm hàng 65% nhưng chưa đạt KPI 80%?","KPI_THRESHOLDS","Chỉ TDV dùng 65%."),
    _case(52,"KPI","manager","Bao nhiêu QLV/cấp quản lý qua cổng thưởng nhóm hàng 70% nhưng chưa đạt KPI 80%?","KPI_THRESHOLDS","Vai trò quản lý dùng 70%."),
    _case(53,"KPI","tp","Top 20 nhân viên theo tỷ lệ hoàn thành tháng 7; ai có target bằng 0 phải tách riêng.","KPI_EMPLOYEE","Không xếp hạng phần trăm khi target 0."),
    _case(54,"KPI","tp","20 nhân viên có tỷ lệ hoàn thành thấp nhất nhưng vẫn có doanh số?","KPI_EMPLOYEE","Lọc Actual>0, Target>0 và xếp tăng dần."),
    _case(55,"KPI","qlv","Doanh số từng ngày của nhân viên tốt nhất đội trong tháng 7 có ngày nào bằng 0?","KPI_DAILY","SQL chỉ trả ngày có phát sinh; ngày 0 cần calendar nếu kết luận."),
    _case(56,"KPI","manager","Đội nào có nhiều khách hoạt động nhất nhưng tỷ lệ hoàn thành thấp hơn 80%?","KPI_CUSTOMER_FLAGS","Kết hợp active customers với KPI đội."),
    _case(57,"KPI","manager","Nhân viên nào có nhiều khách mới nhưng doanh số thấp hơn trung vị đội?","KPI_CUSTOMER_FLAGS","Không đánh đồng số khách mới với doanh số."),
    _case(58,"KPI","c_level","Tổng doanh số theo tầng TP, QLV và nhân viên tuyến dưới có bằng nhau không; vì sao không cộng các tầng?","KPI_LAYER_RECON","Nêu rõ roll-up chồng tầng."),
    _case(59,"KPI","manager","Có nhân viên trùng mã nào làm nguy cơ đếm KPI hai lần không?","KPI_DUPLICATE","Đối chiếu cờ duplicate/resigned."),
    _case(60,"KPI","qlv","Nếu một TDV đạt 67%, phải mô tả trạng thái thưởng nhóm hàng, KPI và chỉ tiêu thế nào?","KPI_THRESHOLDS","Đúng: qua 65%, chưa KPI 80%, chưa chỉ tiêu 100%."),
    _case(61,"KPI","manager","Nếu một QLV đạt 67%, họ đã qua cổng thưởng nhóm hàng chưa?","KPI_THRESHOLDS","Đúng: chưa qua cổng 70%; không nói đạt KPI."),
    _case(62,"KPI","c_level","Nhân viên nào thiếu quan hệ quản lý khiến chatbot không thể xác định đúng đội?","KPI_QUALITY","Phải báo thiếu dữ liệu tổ chức, không trả đội doanh thu 0."),

    # 63-76: lương thưởng
    _case(63,"Lương thưởng","manager","Chi tiết thưởng kinh doanh và phụ cấp tháng 7 của từng nhân viên gồm những khoản nào?","SALARY_DETAIL","Không gọi đây là tổng lương/tổng thu nhập vì thiếu LCB."),
    _case(64,"Lương thưởng","c_level","Top 30 nhân viên có tổng thưởng kinh doanh cao nhất tháng 7?","SALARY_RANK","TotalBonus chỉ gồm DM+V15+V22+V25+ASO."),
    _case(65,"Lương thưởng","manager","Ai có thưởng V15 cao nhất, tỷ lệ V15 và số tiền đã chốt là bao nhiêu?","SALARY_PROGRESS","Phân biệt tỷ lệ với bonus đã lưu."),
    _case(66,"Lương thưởng","manager","Ai có thưởng V22 cao nhất, tỷ lệ V22 và số tiền đã chốt là bao nhiêu?","SALARY_PROGRESS","Phân biệt tỷ lệ với bonus đã lưu."),
    _case(67,"Lương thưởng","manager","Ai có thưởng V25 cao nhất, tỷ lệ V25 và số tiền đã chốt là bao nhiêu?","SALARY_PROGRESS","Phân biệt tỷ lệ với bonus đã lưu."),
    _case(68,"Lương thưởng","manager","Thưởng ASO của từng nhân viên tháng 7 được chốt thế nào; ai không qua điều kiện nào?","SALARY_ASO","ASO là chỉ tiêu/khoản thưởng, không phải chức danh."),
    _case(69,"Lương thưởng","c_level","Tỷ lệ nhân viên có phát sinh V15, V22, V25 và ASO theo vùng/chức danh?","SALARY_ACHIEVEMENT","Mẫu số là số nhân viên cùng snapshot."),
    _case(70,"Lương thưởng","manager","Các bậc tiền thưởng V25 tháng 7 theo vùng và chức danh là gì?","SALARY_RULES","Đọc DIM_BacThuong đúng hiệu lực."),
    _case(71,"Lương thưởng","manager","Công thức V25 dùng doanh số nào, target nào và ngày chốt nào?","SALARY_PROGRESS","Dùng V25Amount/MonthSaleTarget và V25Date thực tế."),
    _case(72,"Lương thưởng","c_level","Có ai tỷ lệ V25 nằm trong bậc có thưởng nhưng V25Bonus đã lưu bằng 0 không?","SALARY_V25_MISMATCH","Phải báo chênh lệch, không tự ghi đè số lương."),
    _case(73,"Lương thưởng","manager","Thưởng danh mục DM1/DM2/DM3 và TotalPoint của từng người khớp nhau thế nào?","SALARY_DETAIL","Đối chiếu DMBonus với các Amount*Percent và TotalPoint."),
    _case(74,"Lương thưởng","manager","Phụ cấp ăn ca, xăng xe, điện thoại tháng 7 của từng người và tổng phụ cấp?","SALARY_DETAIL","Chỉ cộng ba khoản phụ cấp, không nhập vào tiền thưởng."),
    _case(75,"Lương thưởng","c_level","Bảng hiện có đủ dữ liệu để kết luận tổng thu nhập đã gồm lương cơ bản chưa?","SALARY_LCB_SCHEMA","Nếu thiếu mapping LCB phải nói rõ chưa đủ."),
    _case(76,"Lương thưởng","manager","Snapshot nào là kỳ lương đã chốt; có dòng đầu/giữa tháng rỗng dễ bị lấy nhầm không?","SALARY_SNAPSHOTS","Chỉ dùng cuối tháng đã chốt cho báo cáo lương."),

    # 77-84: CTKM
    _case(77,"Khuyến mãi","c_level","Đánh giá hiệu quả từng chương trình khuyến mãi theo doanh thu gắn với đơn, khách tham gia và số đơn.","PROMO_EFFECT","Dùng chuỗi DMS thật; không group ghi chú CTKM hóa đơn."),
    _case(78,"Khuyến mãi","manager","Chương trình nào tháng 12/2025 có nhiều khách tham gia nhất?","PROMO_EFFECT","Xếp theo Customers, không theo số dòng link."),
    _case(79,"Khuyến mãi","manager","Chương trình nào có doanh thu gắn với đơn cao nhưng ít khách tham gia?","PROMO_EFFECT","Nêu associated revenue và giới hạn không phải ROI."),
    _case(80,"Khuyến mãi","manager","Mỗi chương trình có những khách nào tham gia nhiều đơn nhất?","PROMO_CUSTOMERS","Gộp distinct OrderId theo chương trình và khách."),
    _case(81,"Khuyến mãi","manager","Số sản phẩm điều kiện, sản phẩm tặng và tổng lượt tặng của từng chương trình?","PROMO_PRODUCTS","Phân biệt configured product và gift product."),
    _case(82,"Khuyến mãi","c_level","Có bao nhiêu đơn dùng đồng thời nhiều chương trình; điều đó ảnh hưởng cách cộng doanh thu ra sao?","PROMO_OVERLAP","Không cộng ngang associated revenue các CTKM."),
    _case(83,"Khuyến mãi","manager","Chuỗi liên kết đơn hàng–khuyến mãi hiện có dữ liệu đến ngày nào?","PROMO_COVERAGE","Phải công khai LastLinkedOrderDate."),
    _case(84,"Khuyến mãi","c_level","Có bao nhiêu liên kết khuyến mãi mất đơn hàng hoặc mất mã chương trình?","PROMO_QUALITY","MissingOrder/MissingProgram phải được nêu rõ."),

    # 85-90: tồn kho/đơn hàng/chất lượng dữ liệu
    _case(85,"Vận hành dữ liệu","manager","Giá trị và số lượng tồn kho theo chi nhánh hiện tại; chi nhánh nào lớn nhất?","INV_SUMMARY","Không gộp B01 sản xuất vào vùng kinh doanh."),
    _case(86,"Vận hành dữ liệu","manager","Có sản phẩm nào tồn kho âm hoặc giá trị tồn âm không?","INV_NEGATIVE","Liệt kê đúng kho/sản phẩm và giá trị."),
    _case(87,"Vận hành dữ liệu","manager","Những đơn tháng 7 nào chậm từ hai ngày trở lên mới xuất hóa đơn?","ORDER_LAG","Đối chiếu DMSId và dùng ngày đơn–ngày hóa đơn."),
    _case(88,"Vận hành dữ liệu","manager","Những đơn DMS tháng 7 chưa tìm thấy hóa đơn tương ứng là đơn nào và trạng thái gì?","ORDER_NO_INVOICE","Không kết luận thất thoát nếu chưa xét trạng thái/sync."),
    _case(89,"Vận hành dữ liệu","c_level","Mốc dữ liệu mới nhất của doanh thu, KPI, lương và khuyến mãi đang lệch nhau thế nào?","SOURCE_FRESHNESS","Nêu riêng từng nguồn; không dùng mốc mới nhất của nguồn A cho nguồn B."),
    _case(90,"Vận hành dữ liệu","c_level","Nguồn nào hiện chưa đủ độ phủ để trả lời dữ liệu mới nhất và chatbot phải cảnh báo ra sao?","SOURCE_FRESHNESS","CTKM phải nêu source gap; không thay bằng ghi chú hóa đơn hay dự đoán."),
]


_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|MERGE|CREATE|GRANT|REVOKE|EXEC|EXECUTE|"
    r"WAITFOR|DBCC|BULK|OPENROWSET|OPENQUERY|OPENDATASOURCE|XP_CMDSHELL)\b",
    re.IGNORECASE,
)


def validate_catalog() -> list[str]:
    errors: list[str] = []
    ids = [case.id for case in CASES]
    if len(CASES) != 90:
        errors.append(f"Phải có đúng 90 case, hiện có {len(CASES)}.")
    if len(ids) != len(set(ids)):
        errors.append("Case ID bị trùng.")
    expected = [f"Q{i:03d}" for i in range(1, 91)]
    if ids != expected:
        errors.append("Case ID phải liên tục Q001..Q090 và đúng thứ tự.")
    for case in CASES:
        if case.checker_id not in CHECKERS:
            errors.append(f"{case.id}: checker không tồn tại: {case.checker_id}")
        if case.audience not in {"qlv", "tp", "manager", "c_level"}:
            errors.append(f"{case.id}: audience không hợp lệ: {case.audience}")
        if len(case.question.strip()) < 20:
            errors.append(f"{case.id}: câu hỏi quá ngắn.")
    for checker in CHECKERS.values():
        sql = checker.sql.strip()
        if checker.database not in {"bravo", "bravo_sp"}:
            errors.append(f"{checker.id}: database không hợp lệ.")
        if not re.match(r"^(SELECT|WITH)\b", sql, re.IGNORECASE):
            errors.append(f"{checker.id}: SQL không bắt đầu bằng SELECT/WITH.")
        if _FORBIDDEN.search(sql):
            errors.append(f"{checker.id}: SQL chứa từ khóa ghi/nguy hiểm.")
        if ";" in sql.rstrip(";"):
            errors.append(f"{checker.id}: chỉ cho phép một statement.")
    return errors


def _mapped_case_ids(checker_id: str) -> list[str]:
    return [case.id for case in CASES if case.checker_id == checker_id]


def render_markdown() -> str:
    lines = [
        "# Bộ 90 câu hỏi stress test nghiệp vụ chatbot DNH",
        "",
        "> Kỳ kiểm chứng chính: 07/2026 (đã chốt). CTKM: 12/2025 vì liên kết DMS hiện mới phủ đến 09/01/2026.",
        "> Công nợ đọc trực tiếp result set `dbo.usp_DeptAccDueDate_GetData` trên SQL Server; "
        "warehouse chỉ là đối tượng của source-gate đối chiếu.",
        "> Chạy SQL bằng `python scripts/business_stress_suite.py --execute --case Q001`.",
        "> Chạy nhóm công nợ bằng `python scripts/business_stress_suite.py --execute --group "
        "\"Công nợ\" --scope-area MN`; source-gate khác `ok` làm tiến trình trả exit code 1.",
        "",
    ]
    current_group = None
    for case in CASES:
        if case.group != current_group:
            current_group = case.group
            lines.extend([f"## {current_group}", "", "| ID | Vai trò | Câu hỏi | Checker | Tiêu chí chính |", "|---|---|---|---|---|"])
        q = case.question.replace("|", "\\|")
        rule = case.pass_rule.replace("|", "\\|")
        lines.append(f"| {case.id} | {case.audience} | {q} | `{case.checker_id}` | {rule} |")
    lines.extend(["", "## SQL ground truth", ""])
    for checker in CHECKERS.values():
        mapped = ", ".join(_mapped_case_ids(checker.id))
        lines.extend([
            f"### {checker.id} — {checker.title}", "",
            f"Nguồn: `{checker.database}` · Case: {mapped}", "",
        ])
        if checker.notes:
            lines.extend([f"Lưu ý: {checker.notes}", ""])
        if checker.database == "bravo_sp":
            lines.extend([
                "Stored procedure nguồn chạy trực tiếp trên SQL Server:", "",
                "```sql", DEBT_SP_DISPLAY + ";", "```", "",
                "SELECT dưới đây chạy trên result set vừa materialize trong RAM:", "",
            ])
        lines.extend(["```sql", checker.sql, "```", ""])
    return "\n".join(lines).rstrip() + "\n"


_DEBT_SNAPSHOT_CACHE: dict[str, Any] = {}
_SALES_PERIOD_CACHE: list[dict[str, Any]] | None = None


def _debt_snapshot(as_of_date: str | None = None):
    from debt_source import fetch_debt_snapshot

    cache_key = as_of_date or str(dt.date.today())
    if cache_key not in _DEBT_SNAPSHOT_CACHE:
        _DEBT_SNAPSHOT_CACHE[cache_key] = fetch_debt_snapshot(as_of_date)
    return _DEBT_SNAPSHOT_CACHE[cache_key]


def _sales_customer_period() -> list[dict[str, Any]]:
    """Doanh thu Q041 doc truc tiep hai view Total tren SQL Server, khong lay warehouse."""
    global _SALES_PERIOD_CACHE
    if _SALES_PERIOD_CACHE is not None:
        return _SALES_PERIOD_CACHE
    from sqlalchemy import text
    from query_engine import _get_engine

    sql = text("""
        WITH Sales AS (
            SELECT CustomerCode,DocDate,Amount9 FROM dbo.vHoaDonTotal
            WHERE DocDate>='2026-02-01' AND DocDate<'2026-08-01'
            UNION ALL
            SELECT CustomerCode,DocDate,Amount9 FROM dbo.vHoaDonETCTotal
            WHERE DocDate>='2026-02-01' AND DocDate<'2026-08-01'
        )
        SELECT CustomerCode,
               SUM(CASE WHEN DocDate>='2026-05-01' THEN Amount9 ELSE 0 END) RecentRevenue,
               SUM(CASE WHEN DocDate<'2026-05-01' THEN Amount9 ELSE 0 END) PriorRevenue,
               100.0*(SUM(CASE WHEN DocDate>='2026-05-01' THEN Amount9 ELSE 0 END)
                    - SUM(CASE WHEN DocDate<'2026-05-01' THEN Amount9 ELSE 0 END))
                    / NULLIF(SUM(CASE WHEN DocDate<'2026-05-01' THEN Amount9 ELSE 0 END),0) ChangePct
        FROM Sales GROUP BY CustomerCode
    """)
    engine = _get_engine("bravo")
    with engine.connect() as connection:
        proxied = connection.connection
        raw = getattr(proxied, "driver_connection", proxied)
        if hasattr(raw, "timeout"):
            raw.timeout = 60
        connection.exec_driver_sql("SET LOCK_TIMEOUT 5000")
        rows = connection.execute(sql).fetchall()
    _SALES_PERIOD_CACHE = [{
        "customer_code": row[0],
        "recent_revenue": float(row[1] or 0),
        "prior_revenue": float(row[2] or 0),
        "change_pct": float(row[3]) if row[3] is not None else None,
    } for row in rows]
    return _SALES_PERIOD_CACHE


def _execute_debt_checker(
    checker: Checker,
    *,
    as_of_date: str | None = None,
    scope_area: str | None = None,
) -> dict[str, Any]:
    started = dt.datetime.now()
    if checker.id == "DEBT_SCOPE_AGING" and not scope_area:
        raise RuntimeError("DEBT_SCOPE_AGING bat buoc co --scope-area MB/MB2/MT/MN.")
    snapshot = _debt_snapshot(as_of_date)
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript("""
            CREATE TABLE fact_congno_khachhang (
                snapshot_date TEXT, snapshot_at TEXT, customer_code TEXT, customer_name TEXT,
                source_class_code TEXT, sales_channel TEXT, area_code TEXT,
                balance_end REAL, overdue_1_15 REAL, overdue_15_30 REAL,
                overdue_30_45 REAL, overdue_gt_45 REAL, total_overdue REAL,
                source_overdue_amount REAL
            );
            CREATE TABLE test_scope (area_code TEXT);
        """)
        columns = (
            "snapshot_date", "snapshot_at", "customer_code", "customer_name",
            "source_class_code", "sales_channel", "area_code", "balance_end",
            "overdue_1_15", "overdue_15_30", "overdue_30_45", "overdue_gt_45",
            "total_overdue", "source_overdue_amount",
        )
        connection.executemany(
            f"INSERT INTO fact_congno_khachhang VALUES ({','.join(['?'] * len(columns))})",
            [tuple(row.get(column) for column in columns) for row in snapshot.rows],
        )
        connection.execute("INSERT INTO test_scope VALUES (?)", (scope_area,))
        if checker.id == "DEBT_RISK":
            connection.execute("""
                CREATE TABLE sales_customer_period (
                    customer_code TEXT, recent_revenue REAL, prior_revenue REAL, change_pct REAL
                )
            """)
            connection.executemany(
                "INSERT INTO sales_customer_period VALUES (?,?,?,?)",
                [(
                    row["customer_code"], row["recent_revenue"], row["prior_revenue"],
                    row["change_pct"],
                ) for row in _sales_customer_period()],
            )
        cursor = connection.execute(checker.sql)
        result_columns = [description[0] for description in cursor.description]
        rows = [list(row) for row in cursor.fetchmany(201)]
    finally:
        connection.close()
    truncated = len(rows) > 200
    rows = rows[:200]
    return {
        "checker_id": checker.id,
        "database": checker.database,
        "status": "ok" if rows else "empty",
        "columns": result_columns,
        "rows": rows,
        "row_count_returned": len(rows),
        "truncated": truncated,
        "duration_ms": int((dt.datetime.now() - started).total_seconds() * 1000),
        "mapped_cases": _mapped_case_ids(checker.id),
        "source": {
            "procedure": snapshot.procedure,
            "parameters": snapshot.parameters,
            "as_of_date": snapshot.as_of_date,
            "executed_at": snapshot.executed_at,
            "source_row_count": len(snapshot.rows),
        },
    }


def _canonical_debt(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[float]]:
    result: dict[tuple[str, str], list[float]] = {}
    numeric = (
        "balance_end", "overdue_1_15", "overdue_15_30", "overdue_30_45",
        "overdue_gt_45", "total_overdue",
    )
    for row in rows:
        key = (str(row.get("customer_code") or ""), str(row.get("sales_channel") or ""))
        totals = result.setdefault(key, [0.0] * len(numeric))
        for index, column in enumerate(numeric):
            totals[index] += float(row.get(column) or 0)
    return result


def _reconcile_debt_source_with_warehouse(snapshot) -> dict[str, Any]:
    """Cổng nghiệm thu: SP live là chuẩn; warehouse chỉ PASS khi khớp snapshot nguồn."""
    from local_warehouse import DB_PATH

    path = Path(DB_PATH)
    if not path.exists():
        return {"status": "warehouse_unavailable", "path": str(path)}
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='fact_congno_khachhang'"
        ).fetchone()
        if not exists:
            return {"status": "warehouse_unavailable", "path": str(path)}
        local_rows = [dict(row) for row in connection.execute(
            "SELECT snapshot_date,snapshot_at,customer_code,sales_channel,area_code,balance_end,"
            "overdue_1_15,overdue_15_30,overdue_30_45,overdue_gt_45,total_overdue "
            "FROM fact_congno_khachhang"
        ).fetchall()]
    finally:
        connection.close()
    if not local_rows:
        return {"status": "warehouse_empty", "path": str(path)}

    source = _canonical_debt(snapshot.rows)
    local = _canonical_debt(local_rows)
    missing_keys = sorted(set(source) - set(local))
    extra_keys = sorted(set(local) - set(source))
    common = set(source) & set(local)
    max_abs_delta = max(
        (abs(source[key][i] - local[key][i]) for key in common for i in range(6)),
        default=0.0,
    )
    local_dates = sorted({str(row.get("snapshot_date") or "") for row in local_rows})
    source_areas = {
        (str(row.get("customer_code") or ""), str(row.get("sales_channel") or "")):
        str(row.get("area_code") or "")
        for row in snapshot.rows
    }
    local_areas = {
        (str(row.get("customer_code") or ""), str(row.get("sales_channel") or "")):
        str(row.get("area_code") or "")
        for row in local_rows
    }
    area_mismatch_keys = sorted(
        key for key in common if source_areas.get(key) != local_areas.get(key)
    )
    local_snapshot_at = max(str(row.get("snapshot_at") or "") for row in local_rows)
    snapshot_lag_seconds = None
    try:
        source_time = dt.datetime.fromisoformat(snapshot.executed_at)
        local_time = dt.datetime.fromisoformat(local_snapshot_at)
        if source_time.tzinfo is not None and local_time.tzinfo is None:
            local_time = local_time.astimezone()
        elif source_time.tzinfo is None and local_time.tzinfo is not None:
            source_time = source_time.astimezone()
        snapshot_lag_seconds = max(0, int((source_time - local_time).total_seconds()))
    except (TypeError, ValueError):
        pass
    try:
        stale_seconds = max(60, int(os.getenv("CHAT_FRESHNESS_STALE_MINUTES", "90")) * 60)
    except ValueError:
        stale_seconds = 90 * 60
    status = "ok"
    if local_dates != [snapshot.as_of_date]:
        status = "snapshot_date_mismatch"
    elif missing_keys or extra_keys or max_abs_delta > 1:
        status = "data_mismatch"
    elif area_mismatch_keys:
        status = "dimension_mismatch"
    elif snapshot_lag_seconds is None or snapshot_lag_seconds > stale_seconds:
        status = "warehouse_stale"
    return {
        "status": status,
        "source_procedure": snapshot.procedure,
        "source_as_of_date": snapshot.as_of_date,
        "source_executed_at": snapshot.executed_at,
        "warehouse_snapshot_dates": local_dates,
        "warehouse_snapshot_at": local_snapshot_at,
        "snapshot_lag_seconds": snapshot_lag_seconds,
        "stale_threshold_seconds": stale_seconds,
        "source_key_count": len(source),
        "warehouse_key_count": len(local),
        "missing_key_count": len(missing_keys),
        "extra_key_count": len(extra_keys),
        "max_abs_value_delta": max_abs_delta,
        "area_mismatch_count": len(area_mismatch_keys),
        "missing_key_sample": missing_keys[:10],
        "extra_key_sample": extra_keys[:10],
        "area_mismatch_sample": area_mismatch_keys[:10],
    }


def _execute_checker(
    checker: Checker,
    *,
    as_of_date: str | None = None,
    scope_area: str | None = None,
) -> dict[str, Any]:
    if checker.database == "bravo_sp":
        return _execute_debt_checker(
            checker, as_of_date=as_of_date, scope_area=scope_area
        )
    from sqlalchemy import text
    from query_engine import _get_engine

    started = dt.datetime.now()
    engine = _get_engine(checker.database)
    with engine.connect() as conn:
        if checker.database == "bravo":
            proxied = conn.connection
            raw = getattr(proxied, "driver_connection", proxied)
            if hasattr(raw, "timeout"):
                raw.timeout = 60
            conn.exec_driver_sql("SET LOCK_TIMEOUT 5000")
        result = conn.execute(text(checker.sql))
        columns = list(result.keys())
        rows = [list(row) for row in result.fetchmany(201)]
    truncated = len(rows) > 200
    rows = rows[:200]
    return {
        "checker_id": checker.id,
        "database": checker.database,
        "status": "ok" if rows else "empty",
        "columns": columns,
        "rows": rows,
        "row_count_returned": len(rows),
        "truncated": truncated,
        "duration_ms": int((dt.datetime.now() - started).total_seconds() * 1000),
        "mapped_cases": _mapped_case_ids(checker.id),
    }


def _selected_cases(args: argparse.Namespace) -> list[BusinessCase]:
    if args.smoke:
        smoke_ids = {"Q001","Q005","Q025","Q037","Q041","Q049","Q063","Q072","Q077","Q089"}
        return [case for case in CASES if case.id in smoke_ids]
    selected = CASES
    if args.case:
        wanted = {value.upper() for value in args.case}
        selected = [case for case in selected if case.id in wanted]
    if args.group:
        needle = args.group.casefold()
        selected = [case for case in selected if needle in case.group.casefold()]
    if not args.all and not args.case and not args.group and not args.smoke:
        return []
    return selected


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true", help="Kiểm tra đủ 90 case và mapping ground truth SQL Server.")
    parser.add_argument("--list", action="store_true", help="In danh sách 90 câu hỏi.")
    parser.add_argument("--show-sql", metavar="CASE_ID", help="In SQL ground truth của một case.")
    parser.add_argument("--export-doc", metavar="PATH", help="Xuất tài liệu Markdown đầy đủ.")
    parser.add_argument("--execute", action="store_true", help="Thực thi checker đã chọn.")
    parser.add_argument("--case", action="append", help="Case cần chạy, có thể lặp tham số.")
    parser.add_argument("--group", help="Chạy một nhóm nghiệp vụ.")
    parser.add_argument("--smoke", action="store_true", help="Chạy 10 checker đại diện.")
    parser.add_argument("--all", action="store_true", help="Chạy toàn bộ checker (mỗi checker chỉ chạy một lần).")
    parser.add_argument("--as-of", help="Ngày chốt SP công nợ YYYY-MM-DD; mặc định hôm nay.")
    parser.add_argument("--scope-area", help="Phạm vi MB/MB2/MT/MN, bắt buộc cho Q042.")
    parser.add_argument("--output", help="Ghi kết quả JSON; mặc định chỉ in tóm tắt.")
    args = parser.parse_args()

    if args.as_of:
        try:
            dt.date.fromisoformat(args.as_of)
        except ValueError:
            print("[ERROR] --as-of phải có định dạng YYYY-MM-DD.")
            return 2
    if args.scope_area and args.scope_area.upper() not in {"MB", "MB2", "MT", "MN"}:
        print("[ERROR] --scope-area chỉ nhận MB, MB2, MT hoặc MN.")
        return 2

    errors = validate_catalog()
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        return 2
    if args.validate:
        direct_count = sum(checker.database == "bravo" for checker in CHECKERS.values())
        sp_count = sum(checker.database == "bravo_sp" for checker in CHECKERS.values())
        print(
            f"VALID: {len(CASES)} cases, {len(CHECKERS)} checkers "
            f"({direct_count} SQL Server SELECT, {sp_count} SQL Server SP-result SELECT)"
        )

    if args.list:
        for case in CASES:
            print(f"{case.id} [{case.audience}/{case.group}] {case.question} -> {case.checker_id}")

    if args.show_sql:
        case = next((item for item in CASES if item.id == args.show_sql.upper()), None)
        if not case:
            print(f"Không tìm thấy case {args.show_sql}")
            return 2
        checker = CHECKERS[case.checker_id]
        print(f"-- {case.id}: {case.question}")
        print(f"-- database={checker.database}; checker={checker.id}; {checker.title}")
        if checker.notes:
            print(f"-- {checker.notes}")
        if checker.database == "bravo_sp":
            print(f"-- SQL Server source (hard-coded, rollback):\n{DEBT_SP_DISPLAY};")
            print("-- SELECT below runs on the SP result set materialized in RAM:")
        print(checker.sql)

    if args.export_doc:
        destination = Path(args.export_doc)
        if not destination.is_absolute():
            destination = ROOT / destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_markdown(), encoding="utf-8")
        print(f"WROTE {destination}")

    if args.execute:
        selected = _selected_cases(args)
        if not selected:
            print("Phải chọn --case, --group, --smoke hoặc --all khi dùng --execute.")
            return 2
        checker_ids = list(dict.fromkeys(case.checker_id for case in selected))
        output = {
            "generated_at": dt.datetime.now().isoformat(),
            "case_count": len(selected),
            "checker_count": len(checker_ids),
            "results": [],
        }
        failed = False
        debt_checker_ids = [
            checker_id for checker_id in checker_ids
            if CHECKERS[checker_id].database == "bravo_sp"
        ]
        if debt_checker_ids:
            try:
                debt_snapshot = _debt_snapshot(args.as_of)
                reconciliation = _reconcile_debt_source_with_warehouse(debt_snapshot)
                output["debt_source_reconciliation"] = reconciliation
                recon_status = reconciliation.get("status")
                print(f"[SOURCE-GATE] debt SP -> warehouse: {recon_status}")
                if recon_status != "ok":
                    failed = True
            except Exception as exc:
                failed = True
                output["debt_source_reconciliation"] = {
                    "status": "error",
                    "error": str(exc),
                }
                print(f"[SOURCE-GATE] debt SP -> warehouse: FAIL {exc}")
        for index, checker_id in enumerate(checker_ids, 1):
            checker = CHECKERS[checker_id]
            print(f"[{index}/{len(checker_ids)}] {checker_id} ({checker.database}) ...", end="", flush=True)
            try:
                result = _execute_checker(
                    checker,
                    as_of_date=args.as_of,
                    scope_area=(args.scope_area or "").upper() or None,
                )
                output["results"].append(result)
                state = "OK" if result["status"] == "ok" else "EMPTY"
                print(f" {state} {result['row_count_returned']} rows / {result['duration_ms']} ms")
            except Exception as exc:
                failed = True
                output["results"].append({
                    "checker_id": checker_id,
                    "database": checker.database,
                    "error": str(exc),
                    "mapped_cases": _mapped_case_ids(checker_id),
                })
                print(f" FAIL {exc}")
        if args.output:
            destination = Path(args.output)
            if not destination.is_absolute():
                destination = ROOT / destination
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print(f"WROTE {destination}")
        return 1 if failed else 0

    if not any((args.validate,args.list,args.show_sql,args.export_doc,args.execute)):
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
