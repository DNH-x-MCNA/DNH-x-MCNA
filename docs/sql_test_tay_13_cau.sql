/* ==================================================================
   SQL DOI CHUNG — 13 CAU CAN TEST LAI (bo dap an da sua 03-04/09/2026)
   Sinh tu: docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md
   Cach dung: chay TOAN BO file trong MOT session SSMS.
     - Buoc 1 tao #sales, cac buoc sau dung lai bang tam do.
     - Doi ky bang cach sua @MonthStart o Buoc 1.
   ================================================================== */

-- ================= BUOC 1: THAM SO + LOP BAN HANG #sales =================
DECLARE @FromDate date = '2025-09-01';
DECLARE @ToDate date = '2026-09-01';
DECLARE @MonthStart date = '2026-08-01';
DECLARE @MonthEnd date = DATEADD(month, 1, @MonthStart);
DECLARE @AsOfDate date = CASE WHEN CONVERT(date,GETDATE())>=@MonthStart AND CONVERT(date,GETDATE())<@MonthEnd THEN CONVERT(date,GETDATE()) ELSE DATEADD(day,-1,@MonthEnd) END;
DECLARE @AreaCode varchar(24) = NULL;
DECLARE @ManagerCode varchar(24) = NULL;
DECLARE @EmployeeCode varchar(24) = NULL;
DECLARE @Channel varchar(3) = NULL;

IF OBJECT_ID('tempdb..#sales') IS NOT NULL DROP TABLE #sales;
SELECT s.Channel, s.DocDate, s.OrderKey, s.Stt, s.CustomerCode, s.ItemCode,
       CONVERT(varchar(50), s.GroupCode) GroupCode, s.BranchCode, s.DistributorCode,
       s.EmpDMSCode, s.Quantity, s.UnitPrice, s.Amount9, s.DocCode, s.DMSId,
       s.DiscountRate,
       tp.CityName,
       CASE WHEN tp.AreaCode IN ('MB','MB1','MB2') THEN 'MB'
            WHEN tp.AreaCode IN ('MT','MN') THEN tp.AreaCode
            ELSE 'CHUA_XAC_DINH' END AreaCode
INTO #sales
FROM (
    SELECT 'OTC' Channel, DocDate, CONCAT('OTC|', Stt) OrderKey, Stt,
           CustomerCode, ItemCode, CONVERT(varchar(50), GroupCode) GroupCode,
           BranchCode, DistributorCode,
           EmpDMSCode, Quantity, UnitPrice, Amount9, DocCode, DMSId, DiscountRate
    FROM dbo.vHoaDonTotal
    WHERE DocDate >= @FromDate AND DocDate < @ToDate
    UNION ALL
    SELECT 'ETC', DocDate, CONCAT('ETC|', Stt), Stt,
           CustomerCode, ItemCode, CONVERT(varchar(50), GroupCode) GroupCode,
           BranchCode, DistributorCode,
           EmpDMSCode, Quantity, UnitPrice, Amount9, DocCode, DMSId, DiscountRate
    FROM dbo.vHoaDonETCTotal
    WHERE DocDate >= @FromDate AND DocDate < @ToDate
) s
OUTER APPLY (
    SELECT TOP (1) c.CityId
    FROM (
        SELECT CityId FROM dbo.DMS_KhachHang WHERE Code = s.CustomerCode
        UNION ALL
        SELECT CityId FROM dbo.DMSSX_KhachHang WHERE Code = s.CustomerCode
    ) c
) kh
LEFT JOIN dbo.DIM_TinhThanhPho tp ON tp.CityId = kh.CityId;
DELETE FROM #sales
WHERE (@Channel IS NOT NULL AND Channel <> @Channel)
   OR (@AreaCode IS NOT NULL AND AreaCode <> @AreaCode);

SELECT COUNT(*) AS SoDongSales FROM #sales;  -- kiem tra da dung bang tam


/* ================================================================
   C13  ->  S87  [PARTIAL]
   Doanh thu gộp, chiết khấu, khuyến mãi, hàng trả và doanh thu thuần từng tháng là bao nhiêu?
   ================================================================ */
SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,Channel,
       SUM(CASE WHEN Amount9>0 THEN Amount9 ELSE 0 END) DoanhThuGop,
       SUM(CASE WHEN Amount9>0 THEN Amount9*ISNULL(DiscountRate,0) ELSE 0 END) ChietKhau,
       SUM(CASE WHEN Amount9<0 OR DocCode='HC' THEN Amount9 ELSE 0 END) HangTraDieuChinh,
       SUM(Amount9)
         - SUM(CASE WHEN Amount9>0 THEN Amount9*ISNULL(DiscountRate,0) ELSE 0 END) DoanhThuThuan
FROM #sales
GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1),Channel
ORDER BY MonthStart,Channel;


/* ================================================================
   C16  ->  S11  [READY]
   Giá bán thực tế bình quân của từng SKU thay đổi MoM/YoY ra sao; SKU nào có dấu hiệu giảm giá hoặc xói mòn giá?
   ================================================================ */
-- --- cau lenh 1/2 ---
SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,Channel,ItemCode,
       SUM(Amount9) Revenue,SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END) PaidQty,
       SUM(Amount9)/NULLIF(SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END),0) RealizedPrice
FROM #sales WHERE UnitPrice>0
GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1),Channel,ItemCode
ORDER BY ItemCode,MonthStart;

-- --- cau lenh 2/2 ---
WITH m AS (
  SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,Channel,ItemCode,
         SUM(Amount9)/NULLIF(SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END),0) RealizedPrice
  FROM #sales WHERE UnitPrice>0
  GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1),Channel,ItemCode
  HAVING SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END)>0
), win AS (
  SELECT *,
    CASE WHEN RealizedPrice<LAG(RealizedPrice) OVER(PARTITION BY Channel,ItemCode ORDER BY MonthStart)
         THEN 1 ELSE 0 END IsDown,
    FIRST_VALUE(RealizedPrice) OVER(PARTITION BY Channel,ItemCode ORDER BY MonthStart
      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) FirstPrice,
    LAST_VALUE(RealizedPrice) OVER(PARTITION BY Channel,ItemCode ORDER BY MonthStart
      ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) LastPrice,
    COUNT(*) OVER(PARTITION BY Channel,ItemCode) MonthsInWindow
  FROM m WHERE MonthStart>=DATEADD(month,-2,@MonthStart) AND MonthStart<=@MonthStart
), g AS (
  SELECT *,ROW_NUMBER() OVER(PARTITION BY Channel,ItemCode ORDER BY MonthStart)
           -ROW_NUMBER() OVER(PARTITION BY Channel,ItemCode,IsDown ORDER BY MonthStart) Grp
  FROM win WHERE IsDown=1
), streak AS (
  SELECT Channel,ItemCode,MAX(cnt) MaxDownStreak
  FROM (SELECT Channel,ItemCode,Grp,COUNT(*) cnt FROM g GROUP BY Channel,ItemCode,Grp) x
  GROUP BY Channel,ItemCode
), agg AS (
  SELECT DISTINCT Channel,ItemCode,FirstPrice,LastPrice,MonthsInWindow FROM win
)
SELECT a.Channel,a.ItemCode,a.MonthsInWindow,a.FirstPrice,a.LastPrice,
       a.LastPrice-a.FirstPrice PriceDelta,
       100.0*(a.LastPrice-a.FirstPrice)/NULLIF(a.FirstPrice,0) PriceChangePct,
       ISNULL(s.MaxDownStreak,0) MaxDownStreak,
       CASE WHEN ISNULL(s.MaxDownStreak,0)>=a.MonthsInWindow-1 THEN 'XOI_MON_LIEN_TUC'
            ELSE 'XOI_MON_KHONG_LIEN_TUC' END XoiMonFlag
FROM agg a LEFT JOIN streak s ON s.Channel=a.Channel AND s.ItemCode=a.ItemCode
WHERE a.MonthsInWindow>=2 AND a.LastPrice<a.FirstPrice
ORDER BY PriceChangePct;


/* ================================================================
   C20  ->  S13  [DERIVED]
   Tăng trưởng trên cùng tập khách hàng và cùng tập sản phẩm (like-for-like) là bao nhiêu, tách khỏi tăng trưởng do mở mới?
   ================================================================ */
-- --- cau lenh 1/2 ---
WITH c AS (
  SELECT CustomerCode,
    SUM(CASE WHEN DocDate>=@MonthStart AND DocDate<@MonthEnd THEN Amount9 ELSE 0 END) Cur,
    SUM(CASE WHEN DocDate>=DATEADD(year,-1,@MonthStart)
              AND DocDate<DATEADD(year,-1,@MonthEnd) THEN Amount9 ELSE 0 END) PY
  FROM #sales GROUP BY CustomerCode
)
SELECT SUM(Cur) CurRevenue,SUM(PY) PYRevenue,
       100.0*(SUM(Cur)-SUM(PY))/NULLIF(SUM(PY),0) LikeForLikeYoYPct
FROM c WHERE Cur<>0 AND PY<>0;

-- --- cau lenh 2/2 ---
WITH w AS (
  SELECT CustomerCode,
    SUM(CASE WHEN DocDate>=DATEADD(month,-3,@MonthEnd)
              AND DocDate<@MonthEnd THEN Amount9 ELSE 0 END) Cur,
    SUM(CASE WHEN DocDate>=DATEADD(month,-6,@MonthEnd)
              AND DocDate<DATEADD(month,-3,@MonthEnd) THEN Amount9 ELSE 0 END) Pre
  FROM #sales GROUP BY CustomerCode
), agg AS (
  SELECT SUM(Cur) CurAll,SUM(Pre) PreAll,
         SUM(CASE WHEN Pre<>0 THEN Cur-Pre ELSE 0 END) LFLDelta,
         COUNT(CASE WHEN Pre<>0 THEN 1 END) LFLCustomers,
         SUM(CASE WHEN Pre<>0 AND Cur=0 THEN -Pre ELSE 0 END) ChurnDelta,
         COUNT(CASE WHEN Pre<>0 AND Cur=0 THEN 1 END) ChurnCustomers,
         SUM(CASE WHEN Pre=0 THEN Cur ELSE 0 END) NewDelta,
         COUNT(CASE WHEN Pre=0 AND Cur<>0 THEN 1 END) NewCustomers
  FROM w
)
SELECT 1 Thu_Tu,'Doanh thu ky nay (3 thang)' CauPhan,CurAll GiaTri,NULL SoKhach FROM agg
UNION ALL SELECT 2,'Doanh thu ky truoc (3 thang lien truoc)',PreAll,NULL FROM agg
UNION ALL SELECT 3,'Tang truong tong',CurAll-PreAll,NULL FROM agg
UNION ALL SELECT 4,'Like-for-like (khach co DT ky truoc)',LFLDelta,LFLCustomers FROM agg
UNION ALL SELECT 5,'  trong do: khach roi bo han (ve 0)',ChurnDelta,ChurnCustomers FROM agg
UNION ALL SELECT 6,'Tang truong tu khach mo moi',NewDelta,NewCustomers FROM agg
UNION ALL SELECT 7,'Kiem tra: LFL + Mo moi - Tang truong tong',
                  LFLDelta+NewDelta-(CurAll-PreAll),NULL FROM agg
ORDER BY Thu_Tu;


/* ================================================================
   C27  ->  S17  [PARTIAL]
   Có sự dịch chuyển doanh thu bất thường giữa kênh, miền, chi nhánh hoặc mã nhân viên qua các tháng không?
   ================================================================ */
-- --- cau lenh 1/3 ---
SELECT CustomerCode,EOMONTH(DocDate) MonthEnd,
       COUNT(DISTINCT EmpDMSCode) EmployeeCodes,COUNT(DISTINCT AreaCode) Areas,
       SUM(Amount9) Revenue
FROM #sales GROUP BY CustomerCode,EOMONTH(DocDate)
HAVING COUNT(DISTINCT EmpDMSCode)>1 OR COUNT(DISTINCT AreaCode)>1;

-- --- cau lenh 2/3 ---
WITH d AS (
  SELECT 'KENH' Chieu,Channel DonVi,EOMONTH(DocDate) MonthEnd,SUM(Amount9) Revenue
  FROM #sales GROUP BY Channel,EOMONTH(DocDate)
  UNION ALL
  SELECT 'MIEN',AreaCode,EOMONTH(DocDate),SUM(Amount9)
  FROM #sales GROUP BY AreaCode,EOMONTH(DocDate)
  UNION ALL
  SELECT 'CHI_NHANH',BranchCode,EOMONTH(DocDate),SUM(Amount9)
  FROM #sales GROUP BY BranchCode,EOMONTH(DocDate)
  UNION ALL
  SELECT 'NHAN_VIEN',EmpDMSCode,EOMONTH(DocDate),SUM(Amount9)
  FROM #sales WHERE EmpDMSCode IS NOT NULL AND LTRIM(RTRIM(EmpDMSCode))<>''
  GROUP BY EmpDMSCode,EOMONTH(DocDate)
), m AS (
  SELECT *,LAG(Revenue) OVER(PARTITION BY Chieu,DonVi ORDER BY MonthEnd) PrevRevenue
  FROM d
)
SELECT Chieu,DonVi,MonthEnd,PrevRevenue,Revenue,
       Revenue-PrevRevenue Delta,
       100.0*(Revenue-PrevRevenue)/NULLIF(ABS(PrevRevenue),0) MoMPct
FROM m
WHERE PrevRevenue IS NOT NULL
  AND ABS(Revenue-PrevRevenue)>=1000000000
  AND ABS(100.0*(Revenue-PrevRevenue)/NULLIF(ABS(PrevRevenue),0))>=25
ORDER BY ABS(Revenue-PrevRevenue) DESC;

-- --- cau lenh 3/3 ---
WITH per AS (
  SELECT CustomerCode,EmpDMSCode,AreaCode,Amount9,
         CASE WHEN DocDate>=DATEADD(month,-3,@MonthEnd) THEN 'CUR' ELSE 'PRE' END Ky
  FROM #sales
  WHERE DocDate>=DATEADD(month,-6,@MonthEnd) AND DocDate<@MonthEnd
), agg AS (
  SELECT CustomerCode,Ky,SUM(Amount9) Rev,
         MIN(EmpDMSCode) EmpMin,MAX(EmpDMSCode) EmpMax,
         MIN(AreaCode) AreaMin,MAX(AreaCode) AreaMax
  FROM per GROUP BY CustomerCode,Ky
), piv AS (
  SELECT CustomerCode,
    SUM(CASE WHEN Ky='CUR' THEN Rev ELSE 0 END) Cur,
    SUM(CASE WHEN Ky='PRE' THEN Rev ELSE 0 END) Pre,
    MAX(CASE WHEN Ky='CUR' THEN EmpMin END) EmpCurMin,
    MAX(CASE WHEN Ky='CUR' THEN EmpMax END) EmpCurMax,
    MAX(CASE WHEN Ky='PRE' THEN EmpMin END) EmpPreMin,
    MAX(CASE WHEN Ky='PRE' THEN EmpMax END) EmpPreMax,
    MAX(CASE WHEN Ky='CUR' THEN AreaMin END) AreaCurMin,
    MAX(CASE WHEN Ky='CUR' THEN AreaMax END) AreaCurMax,
    MAX(CASE WHEN Ky='PRE' THEN AreaMin END) AreaPreMin,
    MAX(CASE WHEN Ky='PRE' THEN AreaMax END) AreaPreMax
  FROM agg GROUP BY CustomerCode
), phanloai AS (
  SELECT *,
    CASE
      WHEN Pre=0 OR Cur=0 THEN 'LOAI_moi_hoac_roi_bo'
      WHEN EmpCurMin=EmpCurMax AND EmpPreMin=EmpPreMax AND EmpCurMin=EmpPreMin
       AND AreaCurMin=AreaCurMax AND AreaPreMin=AreaPreMax AND AreaCurMin=AreaPreMin
        THEN 'ON_DINH_khong_xao_tron'
      ELSE 'LOAI_doi_NV_hoac_dia_ban'
    END Nhom
  FROM piv
)
SELECT Nhom,COUNT(*) SoKhach,SUM(Pre) DoanhThuKyTruoc,SUM(Cur) DoanhThuKyNay,
       SUM(Cur)-SUM(Pre) Delta,
       100.0*(SUM(Cur)-SUM(Pre))/NULLIF(SUM(Pre),0) TangTruongPct
FROM phanloai GROUP BY Nhom
ORDER BY Nhom;


/* ================================================================
   C28  ->  S17  [PARTIAL]
   Nếu loại ảnh hưởng của thay đổi địa bàn, chuyển nhân viên và chuyển khách, tăng trưởng thực của từng đơn vị còn bao nhiêu?
   ================================================================ */
-- --- cau lenh 1/3 ---
SELECT CustomerCode,EOMONTH(DocDate) MonthEnd,
       COUNT(DISTINCT EmpDMSCode) EmployeeCodes,COUNT(DISTINCT AreaCode) Areas,
       SUM(Amount9) Revenue
FROM #sales GROUP BY CustomerCode,EOMONTH(DocDate)
HAVING COUNT(DISTINCT EmpDMSCode)>1 OR COUNT(DISTINCT AreaCode)>1;

-- --- cau lenh 2/3 ---
WITH d AS (
  SELECT 'KENH' Chieu,Channel DonVi,EOMONTH(DocDate) MonthEnd,SUM(Amount9) Revenue
  FROM #sales GROUP BY Channel,EOMONTH(DocDate)
  UNION ALL
  SELECT 'MIEN',AreaCode,EOMONTH(DocDate),SUM(Amount9)
  FROM #sales GROUP BY AreaCode,EOMONTH(DocDate)
  UNION ALL
  SELECT 'CHI_NHANH',BranchCode,EOMONTH(DocDate),SUM(Amount9)
  FROM #sales GROUP BY BranchCode,EOMONTH(DocDate)
  UNION ALL
  SELECT 'NHAN_VIEN',EmpDMSCode,EOMONTH(DocDate),SUM(Amount9)
  FROM #sales WHERE EmpDMSCode IS NOT NULL AND LTRIM(RTRIM(EmpDMSCode))<>''
  GROUP BY EmpDMSCode,EOMONTH(DocDate)
), m AS (
  SELECT *,LAG(Revenue) OVER(PARTITION BY Chieu,DonVi ORDER BY MonthEnd) PrevRevenue
  FROM d
)
SELECT Chieu,DonVi,MonthEnd,PrevRevenue,Revenue,
       Revenue-PrevRevenue Delta,
       100.0*(Revenue-PrevRevenue)/NULLIF(ABS(PrevRevenue),0) MoMPct
FROM m
WHERE PrevRevenue IS NOT NULL
  AND ABS(Revenue-PrevRevenue)>=1000000000
  AND ABS(100.0*(Revenue-PrevRevenue)/NULLIF(ABS(PrevRevenue),0))>=25
ORDER BY ABS(Revenue-PrevRevenue) DESC;

-- --- cau lenh 3/3 ---
WITH per AS (
  SELECT CustomerCode,EmpDMSCode,AreaCode,Amount9,
         CASE WHEN DocDate>=DATEADD(month,-3,@MonthEnd) THEN 'CUR' ELSE 'PRE' END Ky
  FROM #sales
  WHERE DocDate>=DATEADD(month,-6,@MonthEnd) AND DocDate<@MonthEnd
), agg AS (
  SELECT CustomerCode,Ky,SUM(Amount9) Rev,
         MIN(EmpDMSCode) EmpMin,MAX(EmpDMSCode) EmpMax,
         MIN(AreaCode) AreaMin,MAX(AreaCode) AreaMax
  FROM per GROUP BY CustomerCode,Ky
), piv AS (
  SELECT CustomerCode,
    SUM(CASE WHEN Ky='CUR' THEN Rev ELSE 0 END) Cur,
    SUM(CASE WHEN Ky='PRE' THEN Rev ELSE 0 END) Pre,
    MAX(CASE WHEN Ky='CUR' THEN EmpMin END) EmpCurMin,
    MAX(CASE WHEN Ky='CUR' THEN EmpMax END) EmpCurMax,
    MAX(CASE WHEN Ky='PRE' THEN EmpMin END) EmpPreMin,
    MAX(CASE WHEN Ky='PRE' THEN EmpMax END) EmpPreMax,
    MAX(CASE WHEN Ky='CUR' THEN AreaMin END) AreaCurMin,
    MAX(CASE WHEN Ky='CUR' THEN AreaMax END) AreaCurMax,
    MAX(CASE WHEN Ky='PRE' THEN AreaMin END) AreaPreMin,
    MAX(CASE WHEN Ky='PRE' THEN AreaMax END) AreaPreMax
  FROM agg GROUP BY CustomerCode
), phanloai AS (
  SELECT *,
    CASE
      WHEN Pre=0 OR Cur=0 THEN 'LOAI_moi_hoac_roi_bo'
      WHEN EmpCurMin=EmpCurMax AND EmpPreMin=EmpPreMax AND EmpCurMin=EmpPreMin
       AND AreaCurMin=AreaCurMax AND AreaPreMin=AreaPreMax AND AreaCurMin=AreaPreMin
        THEN 'ON_DINH_khong_xao_tron'
      ELSE 'LOAI_doi_NV_hoac_dia_ban'
    END Nhom
  FROM piv
)
SELECT Nhom,COUNT(*) SoKhach,SUM(Pre) DoanhThuKyTruoc,SUM(Cur) DoanhThuKyNay,
       SUM(Cur)-SUM(Pre) Delta,
       100.0*(SUM(Cur)-SUM(Pre))/NULLIF(SUM(Pre),0) TangTruongPct
FROM phanloai GROUP BY Nhom
ORDER BY Nhom;


/* ================================================================
   C30  ->  S19  [DERIVED]
   Tỷ lệ giữ chân khách theo cohort tháng mở mới sau 1/3/6/12 tháng là bao nhiêu, theo kênh và miền?
   ================================================================ */
-- --- cau lenh 1/2 ---
WITH f AS (
  SELECT CustomerCode,MIN(DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1)) CohortMonth
  FROM #sales GROUP BY CustomerCode
), a AS (
  SELECT DISTINCT CustomerCode,DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) ActiveMonth FROM #sales
)
SELECT f.CohortMonth,DATEDIFF(month,f.CohortMonth,a.ActiveMonth) AgeMonth,
       COUNT(DISTINCT a.CustomerCode) RetainedCustomers
FROM f JOIN a ON a.CustomerCode=f.CustomerCode AND a.ActiveMonth>=f.CohortMonth
GROUP BY f.CohortMonth,DATEDIFF(month,f.CohortMonth,a.ActiveMonth)
ORDER BY f.CohortMonth,AgeMonth;

-- --- cau lenh 2/2 ---
WITH f AS (
  SELECT CustomerCode,MIN(DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1)) CohortMonth
  FROM #sales GROUP BY CustomerCode
), dim AS (
  SELECT f.CustomerCode,f.CohortMonth,MIN(s.Channel) Channel,MIN(s.AreaCode) AreaCode
  FROM f JOIN #sales s ON s.CustomerCode=f.CustomerCode
    AND DATEFROMPARTS(YEAR(s.DocDate),MONTH(s.DocDate),1)=f.CohortMonth
  GROUP BY f.CustomerCode,f.CohortMonth
), a AS (
  SELECT DISTINCT CustomerCode,DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) ActiveMonth
  FROM #sales
), r AS (
  SELECT d.CohortMonth,d.Channel,d.AreaCode,d.CustomerCode,
         DATEDIFF(month,d.CohortMonth,a.ActiveMonth) AgeMonth
  FROM dim d JOIN a ON a.CustomerCode=d.CustomerCode AND a.ActiveMonth>=d.CohortMonth
), sz AS (
  SELECT CohortMonth,Channel,AreaCode,COUNT(*) CohortSize FROM dim
  GROUP BY CohortMonth,Channel,AreaCode
), ret AS (
  SELECT CohortMonth,Channel,AreaCode,
    COUNT(DISTINCT CASE WHEN AgeMonth=1 THEN CustomerCode END) R1,
    COUNT(DISTINCT CASE WHEN AgeMonth=3 THEN CustomerCode END) R3,
    COUNT(DISTINCT CASE WHEN AgeMonth=6 THEN CustomerCode END) R6,
    COUNT(DISTINCT CASE WHEN AgeMonth=12 THEN CustomerCode END) R12
  FROM r GROUP BY CohortMonth,Channel,AreaCode
), m AS (SELECT MAX(ActiveMonth) LastMonth,MIN(ActiveMonth) FirstMonth FROM a)
SELECT s.CohortMonth,s.Channel,s.AreaCode,s.CohortSize,
  CASE WHEN DATEDIFF(month,s.CohortMonth,m.LastMonth)>=1
       THEN 100.0*t.R1/NULLIF(s.CohortSize,0) END GiuChan_1Thang,
  CASE WHEN DATEDIFF(month,s.CohortMonth,m.LastMonth)>=3
       THEN 100.0*t.R3/NULLIF(s.CohortSize,0) END GiuChan_3Thang,
  CASE WHEN DATEDIFF(month,s.CohortMonth,m.LastMonth)>=6
       THEN 100.0*t.R6/NULLIF(s.CohortSize,0) END GiuChan_6Thang,
  CASE WHEN DATEDIFF(month,s.CohortMonth,m.LastMonth)>=12
       THEN 100.0*t.R12/NULLIF(s.CohortSize,0) END GiuChan_12Thang,
  CASE WHEN s.CohortMonth=m.FirstMonth THEN 'KIEM_DUYET_TRAI_khong_dung'
       ELSE 'OK' END GhiChu
FROM sz s
JOIN ret t ON t.CohortMonth=s.CohortMonth AND t.Channel=s.Channel AND t.AreaCode=s.AreaCode
CROSS JOIN m
ORDER BY s.CohortMonth,s.Channel,s.AreaCode;


/* ================================================================
   C34  ->  S22  [DERIVED]
   Doanh thu sản phẩm mới sau 1/3/6/12 tháng ra mắt đạt bao nhiêu so kế hoạch; độ phủ khách hàng ra sao?
   ================================================================ */
-- --- cau lenh 1/2 ---
WITH f AS (
  SELECT ItemCode,MIN(DocDate) FirstSaleDate FROM #sales GROUP BY ItemCode
)
SELECT EOMONTH(f.FirstSaleDate) LaunchMonth,s.ItemCode,
       COUNT(DISTINCT s.CustomerCode) Customers,SUM(s.Amount9) Revenue
FROM f JOIN #sales s ON s.ItemCode=f.ItemCode
  AND s.DocDate>=f.FirstSaleDate AND s.DocDate<DATEADD(month,6,f.FirstSaleDate)
GROUP BY EOMONTH(f.FirstSaleDate),s.ItemCode;

-- --- cau lenh 2/2 ---
WITH f AS (
  SELECT ItemCode,MIN(DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1)) LaunchMonth
  FROM #sales GROUP BY ItemCode
), sm AS (
  SELECT ItemCode,DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,
         SUM(Amount9) Rev,COUNT(DISTINCT CustomerCode) Cus
  FROM #sales GROUP BY ItemCode,DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1)
), a AS (
  SELECT f.LaunchMonth,f.ItemCode,
         DATEDIFF(month,f.LaunchMonth,sm.MonthStart) AgeMonth,sm.Rev,sm.Cus
  FROM f JOIN sm ON sm.ItemCode=f.ItemCode AND sm.MonthStart>=f.LaunchMonth
), m AS (SELECT MIN(MonthStart) FirstMonth,MAX(MonthStart) LastMonth FROM sm)
SELECT a.LaunchMonth,a.ItemCode,
  DATEDIFF(month,a.LaunchMonth,m.LastMonth) TuoiToiDaDatDuoc,
  MAX(CASE WHEN a.AgeMonth=0  THEN a.Rev END) DT_Tuoi0,
  MAX(CASE WHEN a.AgeMonth=0  THEN a.Cus END) Khach_Tuoi0,
  MAX(CASE WHEN a.AgeMonth=1  THEN a.Rev END) DT_Tuoi1,
  MAX(CASE WHEN a.AgeMonth=1  THEN a.Cus END) Khach_Tuoi1,
  MAX(CASE WHEN a.AgeMonth=3  THEN a.Rev END) DT_Tuoi3,
  MAX(CASE WHEN a.AgeMonth=3  THEN a.Cus END) Khach_Tuoi3,
  MAX(CASE WHEN a.AgeMonth=6  THEN a.Rev END) DT_Tuoi6,
  MAX(CASE WHEN a.AgeMonth=6  THEN a.Cus END) Khach_Tuoi6,
  MAX(CASE WHEN a.AgeMonth=12 THEN a.Rev END) DT_Tuoi12,
  MAX(CASE WHEN a.AgeMonth=12 THEN a.Cus END) Khach_Tuoi12,
  CASE WHEN a.LaunchMonth=m.FirstMonth THEN 'KIEM_DUYET_TRAI_khong_dung'
       ELSE 'OK' END GhiChu
FROM a CROSS JOIN m
GROUP BY a.LaunchMonth,a.ItemCode,m.FirstMonth,m.LastMonth
ORDER BY a.LaunchMonth,MAX(CASE WHEN a.AgeMonth=0 THEN a.Rev END) DESC;


/* ================================================================
   C41  ->  S27  [READY_CURRENT]
   Giá trị tồn kho, số tháng tồn, hàng chậm luân chuyển, stock-out và hàng cận date thay đổi thế nào theo tháng?
   ================================================================ */
-- --- cau lenh 1/2 ---
SELECT k.BranchCode,p.Code ItemCode,MAX(p.Name) ProductName,
       SUM(t.Quantity) Quantity,SUM(t.Amount) InventoryValue,
       SUM(CASE WHEN ISNULL(t.Amount,0)=0 AND t.Quantity>0 THEN 1 ELSE 0 END) DongThieuGia
FROM dbo.BRV_TonKhoDK t
LEFT JOIN dbo.BRV_Kho k ON k.Id=t.WarehouseId
LEFT JOIN dbo.BRV_SanPham p ON p.Id=t.ItemId
WHERE t.IsActive=1
GROUP BY k.BranchCode,p.Code ORDER BY InventoryValue DESC;

-- --- cau lenh 2/2 ---
WITH ton AS (
  SELECT p.Code ItemCode,MAX(p.Name) ProductName,SUM(t.Quantity) Qty,SUM(t.Amount) Amount
  FROM dbo.BRV_TonKhoDK t
  LEFT JOIN dbo.BRV_SanPham p ON p.Id=t.ItemId
  WHERE t.IsActive=1 GROUP BY p.Code
), ban AS (
  SELECT ItemCode,
         SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END)/3.0 QtyPerMonth,
         SUM(Amount9) Revenue3M,MAX(DocDate) LastSaleDate
  FROM #sales WHERE DocDate>=DATEADD(month,-3,@MonthEnd) AND DocDate<@MonthEnd
  GROUP BY ItemCode
)
SELECT ISNULL(ton.ItemCode,ban.ItemCode) ItemCode,ton.ProductName,
       ISNULL(ton.Qty,0) TonHienTai,ISNULL(ton.Amount,0) GiaTriTon,
       ISNULL(ban.QtyPerMonth,0) BanBinhQuanThang,
       ton.Qty/NULLIF(ban.QtyPerMonth,0) SoThangTon,
       ban.LastSaleDate,
       CASE WHEN ton.ItemCode IS NULL AND ban.QtyPerMonth>0 THEN 'STOCK_OUT_van_dang_ban'
            WHEN ISNULL(ton.Qty,0)=0 AND ban.QtyPerMonth>0 THEN 'STOCK_OUT_van_dang_ban'
            WHEN ISNULL(ban.QtyPerMonth,0)=0 AND ton.Qty>0 THEN 'TON_KHONG_BAN_3_THANG'
            WHEN ton.Qty/NULLIF(ban.QtyPerMonth,0)>6 THEN 'CHAM_LUAN_CHUYEN'
            ELSE 'BINH_THUONG' END TrangThai
FROM ton FULL OUTER JOIN ban ON ban.ItemCode=ton.ItemCode
WHERE (ISNULL(ton.Qty,0)=0 AND ISNULL(ban.QtyPerMonth,0)>0)
   OR (ISNULL(ban.QtyPerMonth,0)=0 AND ISNULL(ton.Qty,0)>0)
   OR ton.Qty/NULLIF(ban.QtyPerMonth,0)>6
ORDER BY TrangThai,ISNULL(ton.Qty,0) DESC;


/* ================================================================
   C45  ->  S30  [READY]
   Tỷ lệ nhân sự đạt 65/70%, 80%, 100% và 120% KPI từng tháng theo kênh/miền/chức danh là bao nhiêu?
   ================================================================ */
-- --- cau lenh 1/2 ---
WITH b AS (
  SELECT *,DENSE_RANK() OVER(
    PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
  FROM dbo.FACT_ThongKeTinhLuong
  WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
)
SELECT EOMONTH(SaveDate) MonthEnd,AreaCode,PositionCode,
       SUM(MonthSaleAmount) Actual,SUM(MonthSaleTarget) Target,
       100.0*SUM(MonthSaleAmount)/NULLIF(SUM(MonthSaleTarget),0) AchievementPct
FROM b WHERE SnapshotRank=1
  AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
GROUP BY EOMONTH(SaveDate),AreaCode,PositionCode;

-- --- cau lenh 2/2 ---
WITH b AS (
  SELECT *,DENSE_RANK() OVER(
    PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
  FROM dbo.FACT_ThongKeTinhLuong
  WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
), k AS (
  SELECT EOMONTH(SaveDate) MonthEnd,AreaCode,PositionCode,EmployeeCode,
         MonthSalePercent_R,
         CASE WHEN PositionCode='TDV' THEN 0.65 ELSE 0.70 END Gate
  FROM b
  WHERE SnapshotRank=1 AND MonthSaleTarget>0
    AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
)
SELECT MonthEnd,AreaCode,PositionCode,
  COUNT(*) TongNguoiCoTarget,
  SUM(CASE WHEN MonthSalePercent_R>=Gate THEN 1 ELSE 0 END) DatCongThuongNhomHang,
  100.0*SUM(CASE WHEN MonthSalePercent_R>=Gate THEN 1 ELSE 0 END)/COUNT(*) PctCongThuong,
  SUM(CASE WHEN MonthSalePercent_R>=0.8 THEN 1 ELSE 0 END) Dat80,
  100.0*SUM(CASE WHEN MonthSalePercent_R>=0.8 THEN 1 ELSE 0 END)/COUNT(*) Pct80,
  SUM(CASE WHEN MonthSalePercent_R>=1.0 THEN 1 ELSE 0 END) DatChiTieu100,
  100.0*SUM(CASE WHEN MonthSalePercent_R>=1.0 THEN 1 ELSE 0 END)/COUNT(*) Pct100,
  SUM(CASE WHEN MonthSalePercent_R>=1.2 THEN 1 ELSE 0 END) Vuot120,
  100.0*SUM(CASE WHEN MonthSalePercent_R>=1.2 THEN 1 ELSE 0 END)/COUNT(*) Pct120
FROM k GROUP BY MonthEnd,AreaCode,PositionCode
ORDER BY MonthEnd,AreaCode,PositionCode;


/* ================================================================
   C14  ->  S10  [BLOCKED]
   Lợi nhuận gộp và biên lợi nhuận gộp theo tháng, kênh, miền và nhóm sản phẩm thay đổi thế nào?
   ================================================================ */
-- CHECKER BI KHOA CO CHU DICH: chi la truy van do nguon, KHONG ra dap an.
-- Ky vong dung: chatbot NOI RO thieu nguon va khong suy doan so.
SELECT o.name ObjectName,c.name ColumnName,t.name DataType
FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
JOIN sys.types t ON t.user_type_id=c.user_type_id
WHERE o.schema_id=SCHEMA_ID('dbo')
  AND (c.name LIKE '%Cost%' OR c.name LIKE '%GiaVon%' OR c.name LIKE '%Profit%'
    OR c.name LIKE '%LoiNhuan%')
ORDER BY o.name,c.column_id;


/* ================================================================
   C15  ->  S10  [BLOCKED]
   Kênh/miền/sản phẩm nào tăng doanh thu nhưng giảm biên lợi nhuận; nguyên nhân do giá, chiết khấu, giá vốn hay cơ cấu?
   ================================================================ */
-- CHECKER BI KHOA CO CHU DICH: chi la truy van do nguon, KHONG ra dap an.
-- Ky vong dung: chatbot NOI RO thieu nguon va khong suy doan so.
SELECT o.name ObjectName,c.name ColumnName,t.name DataType
FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
JOIN sys.types t ON t.user_type_id=c.user_type_id
WHERE o.schema_id=SCHEMA_ID('dbo')
  AND (c.name LIKE '%Cost%' OR c.name LIKE '%GiaVon%' OR c.name LIKE '%Profit%'
    OR c.name LIKE '%LoiNhuan%')
ORDER BY o.name,c.column_id;


/* ================================================================
   C19  ->  S10  [BLOCKED]
   Sản phẩm/khách hàng nào doanh thu cao nhưng lợi nhuận thấp hoặc âm; tỷ trọng của nhóm này tăng hay giảm?
   ================================================================ */
-- CHECKER BI KHOA CO CHU DICH: chi la truy van do nguon, KHONG ra dap an.
-- Ky vong dung: chatbot NOI RO thieu nguon va khong suy doan so.
SELECT o.name ObjectName,c.name ColumnName,t.name DataType
FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
JOIN sys.types t ON t.user_type_id=c.user_type_id
WHERE o.schema_id=SCHEMA_ID('dbo')
  AND (c.name LIKE '%Cost%' OR c.name LIKE '%GiaVon%' OR c.name LIKE '%Profit%'
    OR c.name LIKE '%LoiNhuan%')
ORDER BY o.name,c.column_id;


/* ================================================================
   C52  ->  S36  [BLOCKED]
   Mỗi kênh/miền cam kết hành động gì để đóng gap; chủ sở hữu, hạn hoàn thành và kết quả tháng sau ra sao?
   ================================================================ */
-- CHECKER BI KHOA CO CHU DICH: chi la truy van do nguon, KHONG ra dap an.
-- Ky vong dung: chatbot NOI RO thieu nguon va khong suy doan so.
SELECT o.name ObjectName,c.name ColumnName
FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
WHERE c.name IN ('Owner','OwnerId','Action','ActionStatus','DueDate','Deadline','Commitment')
   OR o.name LIKE '%Action%' OR o.name LIKE '%Task%'
ORDER BY o.name,c.column_id;
