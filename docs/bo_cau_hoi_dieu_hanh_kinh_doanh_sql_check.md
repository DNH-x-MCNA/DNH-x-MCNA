# Catalog SQL check cho 138 câu hỏi điều hành month-by-month

Tài liệu này đi kèm
[master list](./bo_cau_hoi_dieu_hanh_kinh_doanh_month_by_month.md). Mỗi mã câu hỏi
Cxx/Mxx/Vxx được map tới đúng một checker Sxx ở mục 3. Khi nhiều câu dùng cùng checker, chỉ thay
tham số phạm vi; không viết lại công thức khác nhau cho từng cấp quản lý.

## 1. Quy ước

- Dialect mặc định: SQL Server NH_Report_TM, schema dbo.
- READY: có thể chạy từ bảng/cột đã xác nhận trong catalog hiện tại.
- DERIVED: dữ liệu gốc có, công thức trong SQL là định nghĩa đề xuất và cần DNH chốt.
- PARTIAL: kiểm được một phần; SQL trả thêm cờ phần còn thiếu.
- BLOCKED/BLOCKED_HISTORY: SQL chỉ kiểm tra mức sẵn sàng, không bịa số.
- READY_CURRENT: chỉ kiểm được snapshot hiện tại, không được diễn giải thành lịch sử tháng.
- Mọi truy vấn phải dùng khoảng nửa mở: DocDate >= @FromDate AND DocDate < @ToDate.
- @ToDate là ngày đầu tháng kế tiếp. @AreaCode, @ManagerCode, @EmployeeCode và @Channel để NULL
  khi chạy toàn công ty.
- **Snapshot KPI/lương phải gộp theo TỪNG NHÂN VIÊN trong tháng, không ghim một SaveDate.**
  DNH không ghi snapshot tháng thành một lần mà tách nhiều ngày theo vùng — xác nhận trên Bravo
  ngày 29/07/2026: `SaveDate 2026-07-27` có MB (102 NV) + MN (48 NV) nhưng **không có MT**;
  `SaveDate 2026-07-28` **chỉ có MT** (34 NV). Ghim `SnapshotRank=1` theo tháng (hoặc
  `SaveDate = MAX(SaveDate)`) thì giữa tháng chỉ thấy một vùng, cho ra "toàn đội 48,7%" trong khi
  thực chất là riêng Miền Trung — hụt 43,97 tỷ chỉ tiêu hai miền còn lại, và **không có cảnh báo
  nào** vì vùng biến mất hoàn toàn thì không còn dòng nào để đối chiếu.
  Vì vậy `PARTITION BY` phải kèm `EmployeeCode`, hoặc dùng CTE `latest` gộp `MAX(SaveDate)` theo
  `EmployeeCode` rồi JOIN lại đúng ngày của chính người đó. Đây là lỗi đã sửa trong code
  (`470e3bd`, mở rộng 27/08/2026 sang `src/alerts.py` và `src/etl.py`); tài liệu này đồng bộ theo
  ngày 28/08/2026 — **đừng sửa ngược lại**.
  Lỗi chỉ lộ **giữa tháng**: các tháng đã đóng luôn có một snapshot trọn vẹn nên nhìn qua vẫn đúng.

## 2. Tham số và lớp bán hàng chuẩn

Chạy block này một lần trong cùng session trước các checker dùng #sales. Chỉ tạo bảng tạm trong
tempdb, không ghi vào dữ liệu DNH.

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
           tp.CityName,
           CASE WHEN tp.AreaCode IN ('MB','MB1','MB2') THEN 'MB'
                WHEN tp.AreaCode IN ('MT','MN') THEN tp.AreaCode
                ELSE 'CHUA_XAC_DINH' END AreaCode
    INTO #sales
    FROM (
        SELECT 'OTC' Channel, DocDate, CONCAT('OTC|', Stt) OrderKey, Stt,
               CustomerCode, ItemCode, CONVERT(varchar(50), GroupCode) GroupCode,
               BranchCode, DistributorCode,
               EmpDMSCode, Quantity, UnitPrice, Amount9, DocCode, DMSId
        FROM dbo.vHoaDonTotal
        WHERE DocDate >= @FromDate AND DocDate < @ToDate
        UNION ALL
        SELECT 'ETC', DocDate, CONCAT('ETC|', Stt), Stt,
               CustomerCode, ItemCode, CONVERT(varchar(50), GroupCode) GroupCode,
               BranchCode, DistributorCode,
               EmpDMSCode, Quantity, UnitPrice, Amount9, DocCode, DMSId
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

Lưu ý: DELETE ở trên chỉ tác động #sales trong tempdb. Nếu tài khoản chỉ cho SELECT, bỏ DELETE và
thêm điều kiện scope vào từng checker.

## 3. Thư viện checker SQL

### S01 — Doanh thu tháng, MoM, YoY và CAGR 24 tháng — READY

Checker này **không dùng `#sales`**. `#sales` bị chặn bởi `@FromDate` chung (mặc định 12 tháng), mà
đổi tham số đó thì kéo theo 38 câu khác đổi đáp án — không đáng để phục vụ 2 câu. Vì vậy S01 tự đọc
thẳng hai view hóa đơn với cửa sổ 24 tháng neo vào `@ToDate`.

Bravo có dữ liệu hóa đơn từ **28/06/2022** (50 tháng, xác nhận 03/09/2026), nên 24 tháng là đủ thật
chứ không phải giả định.

Số đơn dùng khóa `Channel + Stt` theo nguyên tắc pass/fail số 4.

    WITH hd AS (
      SELECT 'OTC' Channel,DocDate,CONCAT('OTC|',Stt) OrderKey,CustomerCode,Amount9
      FROM dbo.vHoaDonTotal
      WHERE DocDate>=DATEADD(month,-24,@ToDate) AND DocDate<@ToDate
      UNION ALL
      SELECT 'ETC',DocDate,CONCAT('ETC|',Stt),CustomerCode,Amount9
      FROM dbo.vHoaDonETCTotal
      WHERE DocDate>=DATEADD(month,-24,@ToDate) AND DocDate<@ToDate
    ), m AS (
      SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,Channel,
             SUM(Amount9) Revenue,COUNT(DISTINCT OrderKey) Orders,
             COUNT(DISTINCT CustomerCode) ActiveCustomers
      FROM hd GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1),Channel
      UNION ALL
      SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1),'TOAN_CONG_TY',
             SUM(Amount9),COUNT(DISTINCT OrderKey),COUNT(DISTINCT CustomerCode)
      FROM hd GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1)
    )
    SELECT MonthStart,Channel,Revenue,Orders,ActiveCustomers,
           Revenue-LAG(Revenue) OVER(PARTITION BY Channel ORDER BY MonthStart) MoMDelta,
           100.0*(Revenue-LAG(Revenue) OVER(PARTITION BY Channel ORDER BY MonthStart))
             /NULLIF(LAG(Revenue) OVER(PARTITION BY Channel ORDER BY MonthStart),0) MoMPct,
           Revenue-LAG(Revenue,12) OVER(PARTITION BY Channel ORDER BY MonthStart) YoYDelta,
           100.0*(Revenue-LAG(Revenue,12) OVER(PARTITION BY Channel ORDER BY MonthStart))
             /NULLIF(LAG(Revenue,12) OVER(PARTITION BY Channel ORDER BY MonthStart),0) YoYPct
    FROM m ORDER BY Channel,MonthStart;

Nhịp tăng trưởng cả kỳ (CAGR quy năm) — so 12 tháng gần nhất với 12 tháng liền trước:

    WITH hd AS (
      SELECT 'OTC' Channel,DocDate,Amount9 FROM dbo.vHoaDonTotal
      WHERE DocDate>=DATEADD(month,-24,@ToDate) AND DocDate<@ToDate
      UNION ALL
      SELECT 'ETC',DocDate,Amount9 FROM dbo.vHoaDonETCTotal
      WHERE DocDate>=DATEADD(month,-24,@ToDate) AND DocDate<@ToDate
    ), k AS (
      SELECT Channel,
             SUM(CASE WHEN DocDate>=DATEADD(month,-12,@ToDate) THEN Amount9 ELSE 0 END) Nam1,
             SUM(CASE WHEN DocDate< DATEADD(month,-12,@ToDate) THEN Amount9 ELSE 0 END) Nam0
      FROM hd GROUP BY Channel
      UNION ALL
      SELECT 'TOAN_CONG_TY',
             SUM(CASE WHEN DocDate>=DATEADD(month,-12,@ToDate) THEN Amount9 ELSE 0 END),
             SUM(CASE WHEN DocDate< DATEADD(month,-12,@ToDate) THEN Amount9 ELSE 0 END)
      FROM hd
    )
    SELECT Channel,Nam0 Revenue12ThangTruoc,Nam1 Revenue12ThangGanNhat,
           Nam1-Nam0 Delta,
           100.0*(Nam1-Nam0)/NULLIF(Nam0,0) GrowthPct
    FROM k ORDER BY Channel;

### S02 — Thực hiện so target tháng/YTD — PARTIAL

Chỉ cộng tầng nhân viên tuyến dưới để tránh trùng roll-up. Target ETC toàn kênh phải map riêng.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    ), k AS (
      SELECT EOMONTH(SaveDate) MonthEnd,AreaCode,
             SUM(MonthSaleAmount) Actual,SUM(MonthSaleTarget) Target
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
      GROUP BY EOMONTH(SaveDate),AreaCode
    )
    SELECT MonthEnd,AreaCode,Actual,Target,
           100.0*Actual/NULLIF(Target,0) AchievementPct,Actual-Target Gap
    FROM k ORDER BY MonthEnd,AreaCode;

### S03 — Run-rate và nhịp cần đạt cuối tháng — DERIVED

    WITH x AS (
      SELECT SUM(Amount9) MTDRevenue,
             DATEDIFF(day,@MonthStart,DATEADD(day,1,@AsOfDate)) ElapsedDays,
             DAY(EOMONTH(@MonthStart)) DaysInMonth
      FROM #sales WHERE DocDate>=@MonthStart AND DocDate<=@AsOfDate
    )
    SELECT MTDRevenue,ElapsedDays,DaysInMonth,
           MTDRevenue/NULLIF(ElapsedDays,0) RevenuePerDay,
           MTDRevenue*DaysInMonth/NULLIF(ElapsedDays,0) LinearRunRate
    FROM x;

### S04 — Đóng góp tăng/giảm theo kênh/miền — DERIVED

    WITH a AS (
      SELECT AreaCode,Channel,
        SUM(CASE WHEN DocDate>=@MonthStart AND DocDate<@MonthEnd THEN Amount9 ELSE 0 END) Cur,
        SUM(CASE WHEN DocDate>=DATEADD(month,-1,@MonthStart) AND DocDate<@MonthStart THEN Amount9 ELSE 0 END) Prev
      FROM #sales GROUP BY AreaCode,Channel
    )
    SELECT AreaCode,Channel,Cur,Prev,Cur-Prev Delta,
           100.0*(Cur-Prev)/NULLIF(SUM(Cur-Prev) OVER(),0) ContributionToChangePct
    FROM a ORDER BY Delta DESC;

### S05 — Revenue driver bridge: khách, đơn, lượng, giá trị đơn — DERIVED

    WITH m AS (
      SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,
             COUNT(DISTINCT CustomerCode) Customers,COUNT(DISTINCT OrderKey) Orders,
             SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END) PaidQty,
             SUM(Amount9) Revenue
      FROM #sales GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1)
    )
    SELECT *,Revenue/NULLIF(Orders,0) AOV,1.0*Orders/NULLIF(Customers,0) OrdersPerCustomer,
           Revenue/NULLIF(PaidQty,0) RevenuePerPaidUnit
    FROM m ORDER BY MonthStart;

### S06 — Rolling trend và seasonality — DERIVED

    WITH m AS (
      SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,SUM(Amount9) Revenue
      FROM #sales GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1)
    )
    SELECT MonthStart,Revenue,
      AVG(Revenue) OVER(ORDER BY MonthStart ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) MA3,
      AVG(Revenue) OVER(ORDER BY MonthStart ROWS BETWEEN 5 PRECEDING AND CURRENT ROW) MA6,
      AVG(Revenue) OVER(PARTITION BY MONTH(MonthStart)) SameMonthAverage
    FROM m ORDER BY MonthStart;

### S07 — Số đơn, AOV, khách mua và tần suất — READY

    WITH o AS (
      SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,Channel,
             OrderKey,MAX(CustomerCode) CustomerCode,SUM(Amount9) OrderRevenue
      FROM #sales GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1),Channel,OrderKey
    )
    SELECT MonthStart,Channel,COUNT(*) Orders,COUNT(DISTINCT CustomerCode) Customers,
           SUM(OrderRevenue) Revenue,AVG(CONVERT(decimal(28,2),OrderRevenue)) AOV,
           1.0*COUNT(*)/NULLIF(COUNT(DISTINCT CustomerCode),0) OrdersPerCustomer
    FROM o GROUP BY MonthStart,Channel ORDER BY MonthStart,Channel;

### S08 — Cơ cấu kênh và mức tập trung — READY

    WITH x AS (
      SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,
             Channel,CustomerCode,ItemCode,SUM(Amount9) Revenue
      FROM #sales GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1),Channel,CustomerCode,ItemCode
    )
    SELECT MonthStart,Channel,SUM(Revenue) Revenue,
           100.0*SUM(Revenue)/NULLIF(SUM(SUM(Revenue)) OVER(PARTITION BY MonthStart),0) ChannelMixPct
    FROM x GROUP BY MonthStart,Channel ORDER BY MonthStart,Channel;

    WITH x AS (
      SELECT EOMONTH(DocDate) MonthEnd,CustomerCode,ItemCode,SUM(Amount9) Revenue
      FROM #sales GROUP BY EOMONTH(DocDate),CustomerCode,ItemCode
    ), c AS (
      SELECT MonthEnd,CustomerCode,SUM(Revenue) Revenue,
             ROW_NUMBER() OVER(PARTITION BY MonthEnd ORDER BY SUM(Revenue) DESC) rn
      FROM x GROUP BY MonthEnd,CustomerCode
    ), p AS (
      SELECT MonthEnd,ItemCode,SUM(Revenue) Revenue,
             ROW_NUMBER() OVER(PARTITION BY MonthEnd ORDER BY SUM(Revenue) DESC) rn
      FROM x GROUP BY MonthEnd,ItemCode
    )
    SELECT MonthEnd,'CUSTOMER_TOP10' ConcentrationType,
           100.0*SUM(CASE WHEN rn<=10 THEN Revenue ELSE 0 END)/NULLIF(SUM(Revenue),0) SharePct
    FROM c GROUP BY MonthEnd
    UNION ALL
    SELECT MonthEnd,'PRODUCT_TOP10',
           100.0*SUM(CASE WHEN rn<=10 THEN Revenue ELSE 0 END)/NULLIF(SUM(Revenue),0)
    FROM p GROUP BY MonthEnd;

### S09 — Hàng trả, điều chỉnh và giao dịch bất thường — READY

    SELECT Channel,AreaCode,COUNT(DISTINCT OrderKey) AffectedOrders,
           SUM(CASE WHEN Amount9<0 OR DocCode='HC' THEN Amount9 ELSE 0 END) ReturnAdjustment,
           MAX(ABS(Amount9)) LargestAbsoluteLine
    FROM #sales WHERE DocDate>=@MonthStart AND DocDate<@MonthEnd
    GROUP BY Channel,AreaCode ORDER BY ReturnAdjustment;

### S10 — Kiểm tra nguồn chiết khấu, giá vốn, lợi nhuận — BLOCKED

Không tính lợi nhuận trước khi DNH chốt mapping cột.

    SELECT o.name ObjectName,c.name ColumnName,t.name DataType
    FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
    JOIN sys.types t ON t.user_type_id=c.user_type_id
    WHERE o.schema_id=SCHEMA_ID('dbo')
      AND (c.name LIKE '%Cost%' OR c.name LIKE '%GiaVon%' OR c.name LIKE '%Profit%'
        OR c.name LIKE '%LoiNhuan%' OR c.name LIKE '%Discount%' OR c.name LIKE '%ChietKhau%')
    ORDER BY o.name,c.column_id;

### S11 — Xu hướng giá bán thực tế theo SKU — READY

    SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,Channel,ItemCode,
           SUM(Amount9) Revenue,SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END) PaidQty,
           SUM(Amount9)/NULLIF(SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END),0) RealizedPrice
    FROM #sales WHERE UnitPrice>0
    GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1),Channel,ItemCode
    ORDER BY ItemCode,MonthStart;

### S12 — Hiệu quả khuyến mãi gắn đơn — PARTIAL

AssociatedRevenue không được cộng ngang vì một đơn có thể có nhiều CTKM.

    WITH po AS (
      SELECT x.ProgId,x.OrderId,MAX(h.CustomerCode) CustomerCode,MAX(h.DocDate) DocDate
      FROM dbo.DMS_DonHangCTKM x JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
      WHERE h.DocDate>=@FromDate AND h.DocDate<@ToDate GROUP BY x.ProgId,x.OrderId
    ), inv AS (
      SELECT TRY_CONVERT(int,DMSId) OrderId,SUM(Amount9) Revenue
      FROM #sales WHERE TRY_CONVERT(int,DMSId) IS NOT NULL GROUP BY TRY_CONVERT(int,DMSId)
    )
    SELECT EOMONTH(po.DocDate) MonthEnd,p.Code,p.Name,COUNT(*) Orders,
           COUNT(DISTINCT po.CustomerCode) Customers,SUM(ISNULL(inv.Revenue,0)) AssociatedRevenue
    FROM po JOIN dbo.DMS_CTKM p ON p.Id=po.ProgId LEFT JOIN inv ON inv.OrderId=po.OrderId
    GROUP BY EOMONTH(po.DocDate),p.Code,p.Name;

### S13 — Like-for-like growth trên cùng tập khách — DERIVED

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

### S14 — Xếp hạng, quy mô và streak địa bàn — READY

    WITH m AS (
      SELECT EOMONTH(DocDate) MonthEnd,AreaCode,SUM(Amount9) Revenue
      FROM #sales GROUP BY EOMONTH(DocDate),AreaCode
    )
    SELECT MonthEnd,AreaCode,Revenue,
           DENSE_RANK() OVER(PARTITION BY MonthEnd ORDER BY Revenue DESC) RankNo,
           Revenue-LAG(Revenue) OVER(PARTITION BY AreaCode ORDER BY MonthEnd) MoMDelta
    FROM m ORDER BY MonthEnd,RankNo;

    SELECT EOMONTH(DocDate) MonthEnd,AreaCode,CityName,BranchCode,
           SUM(Amount9) Revenue,COUNT(DISTINCT CustomerCode) ActiveCustomers
    FROM #sales GROUP BY EOMONTH(DocDate),AreaCode,CityName,BranchCode
    ORDER BY MonthEnd,Revenue DESC;

### S15 — Năng suất NPP/chi nhánh — READY

    SELECT EOMONTH(DocDate) MonthEnd,BranchCode,DistributorCode,Channel,
           SUM(Amount9) Revenue,COUNT(DISTINCT OrderKey) Orders,
           COUNT(DISTINCT CustomerCode) Customers
    FROM #sales GROUP BY EOMONTH(DocDate),BranchCode,DistributorCode,Channel
    ORDER BY MonthEnd,Revenue DESC;

### S16 — Khách mua chéo OTC/ETC — READY

    WITH c AS (
      SELECT EOMONTH(DocDate) MonthEnd,CustomerCode,
             COUNT(DISTINCT Channel) Channels,SUM(Amount9) Revenue
      FROM #sales GROUP BY EOMONTH(DocDate),CustomerCode
    )
    SELECT MonthEnd,
           COUNT(*) TotalCustomers,
           SUM(CASE WHEN Channels=2 THEN 1 ELSE 0 END) DualChannelCustomers,
           SUM(CASE WHEN Channels=2 THEN Revenue ELSE 0 END) DualChannelRevenue,
           SUM(Revenue) TotalRevenue,
           100.0*SUM(CASE WHEN Channels=2 THEN Revenue ELSE 0 END)
             /NULLIF(SUM(Revenue),0) DualChannelSharePct
    FROM c GROUP BY MonthEnd ORDER BY MonthEnd;

Bản chạy 28/08/2026 cho `DualChannelCustomers = 0` ở mọi tháng: OTC và ETC là hai tập khách rời
nhau. Trước đây câu lệnh lọc `WHERE Channels=2` nên trả bảng RỖNG — không phân biệt được "không có
khách mua chéo" với "truy vấn hỏng". Nay đếm cả ba nhóm để số 0 là đáp án nhìn thấy được.

### S17 — Thay đổi mapping địa bàn/nhân viên — PARTIAL

Catalog hiện không có bảng lịch sử assignment chuẩn; query này chỉ phát hiện một khách có nhiều mã
nhân viên/vùng trong hóa đơn theo tháng.

    SELECT CustomerCode,EOMONTH(DocDate) MonthEnd,
           COUNT(DISTINCT EmpDMSCode) EmployeeCodes,COUNT(DISTINCT AreaCode) Areas,
           SUM(Amount9) Revenue
    FROM #sales GROUP BY CustomerCode,EOMONTH(DocDate)
    HAVING COUNT(DISTINCT EmpDMSCode)>1 OR COUNT(DISTINCT AreaCode)>1;

### S18 — Khách mới, mua lại, hoạt động — READY

    WITH snaps AS (
      SELECT EOMONTH(SaveDate) MonthEnd,MAX(SaveDate) SaveDate
      FROM dbo.FACT_TongHopKhachHang
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate GROUP BY EOMONTH(SaveDate)
    )
    SELECT EOMONTH(f.SaveDate) MonthEnd,f.AreaCode,f.ManagerCode,
           COUNT(DISTINCT CASE WHEN f.IsNC=1 THEN f.CustomerCode END) NewCustomers,
           COUNT(DISTINCT CASE WHEN f.IsRO=1 THEN f.CustomerCode END) ReorderCustomers,
           COUNT(DISTINCT CASE WHEN f.IsAC=1 THEN f.CustomerCode END) ActiveCustomers
    FROM dbo.FACT_TongHopKhachHang f JOIN snaps s ON s.SaveDate=f.SaveDate
    WHERE (@AreaCode IS NULL OR f.AreaCode=@AreaCode)
      AND (@ManagerCode IS NULL OR f.ManagerCode=@ManagerCode)
    GROUP BY EOMONTH(f.SaveDate),f.AreaCode,f.ManagerCode;

### S19 — Cohort giữ chân khách — DERIVED

Cohort mặc định là tháng có hóa đơn đầu tiên; nếu DNH định nghĩa khách mới khác thì thay nguồn cohort.

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

### S20 — Luồng khách và khách tăng/giảm mạnh — READY

    WITH c AS (
      SELECT CustomerCode,
        SUM(CASE WHEN DocDate>=@MonthStart AND DocDate<@MonthEnd THEN Amount9 ELSE 0 END) Cur,
        SUM(CASE WHEN DocDate>=DATEADD(month,-1,@MonthStart) AND DocDate<@MonthStart THEN Amount9 ELSE 0 END) Prev
      FROM #sales GROUP BY CustomerCode
    )
    SELECT TOP (100) CustomerCode,Cur,Prev,Cur-Prev Delta,
           CASE WHEN Prev=0 AND Cur>0 THEN 'NEW_OR_REACTIVATED'
                WHEN Prev>0 AND Cur=0 THEN 'STOPPED'
                WHEN Cur>Prev THEN 'GROWING' ELSE 'DECLINING' END Movement
    FROM c WHERE Cur<>Prev ORDER BY ABS(Cur-Prev) DESC;

### S21 — Đóng góp tăng/giảm theo nhóm/SKU — READY

    WITH p AS (
      SELECT GroupCode,ItemCode,
        SUM(CASE WHEN DocDate>=@MonthStart AND DocDate<@MonthEnd THEN Amount9 ELSE 0 END) Cur,
        SUM(CASE WHEN DocDate>=DATEADD(month,-1,@MonthStart) AND DocDate<@MonthStart THEN Amount9 ELSE 0 END) Prev
      FROM #sales GROUP BY GroupCode,ItemCode
    )
    SELECT GroupCode,ItemCode,Cur,Prev,Cur-Prev Delta,
           100.0*(Cur-Prev)/NULLIF(SUM(Cur-Prev) OVER(),0) ContributionPct
    FROM p ORDER BY Delta DESC;

### S22 — Sản phẩm mới theo tháng bán đầu tiên — DERIVED

    WITH f AS (
      SELECT ItemCode,MIN(DocDate) FirstSaleDate FROM #sales GROUP BY ItemCode
    )
    SELECT EOMONTH(f.FirstSaleDate) LaunchMonth,s.ItemCode,
           COUNT(DISTINCT s.CustomerCode) Customers,SUM(s.Amount9) Revenue
    FROM f JOIN #sales s ON s.ItemCode=f.ItemCode
      AND s.DocDate>=f.FirstSaleDate AND s.DocDate<DATEADD(month,6,f.FirstSaleDate)
    GROUP BY EOMONTH(f.FirstSaleDate),s.ItemCode;

### S23 — Phụ thuộc và độ phủ SKU — DERIVED

    WITH p AS (
      SELECT EOMONTH(DocDate) MonthEnd,ItemCode,SUM(Amount9) Revenue,
             COUNT(DISTINCT CustomerCode) Customers
      FROM #sales GROUP BY EOMONTH(DocDate),ItemCode
    )
    SELECT MonthEnd,ItemCode,Revenue,Customers,
           100.0*Revenue/NULLIF(SUM(Revenue) OVER(PARTITION BY MonthEnd),0) RevenueSharePct,
           DENSE_RANK() OVER(PARTITION BY MonthEnd ORDER BY Revenue DESC) RankNo
    FROM p ORDER BY MonthEnd,RankNo;

### S24 — Công nợ snapshot hiện tại — READY_CURRENT

Nguồn đúng là SP DNH. Chạy SP để lấy result set thô; các phép tổng hợp hiện có trong
scripts/business_stress_suite.py và kho local fact_congno_khachhang.

    DECLARE @DebtFromDate date = DATEFROMPARTS(YEAR(@AsOfDate),1,1);
    EXEC dbo.usp_DeptAccDueDate_GetData
      @_DocDate1=@DebtFromDate,
      @_DocDate2=@AsOfDate,@_Period1=7,@_Period2=15,
      @_RepType=1,@_IsPrepaymentInclude=1;

    -- Trên kho local sau khi sync:
    SELECT sales_channel,SUM(balance_end) Balance,SUM(total_overdue) Overdue,
           100.0*SUM(total_overdue)/NULLIF(SUM(balance_end),0) OverduePct
    FROM fact_congno_khachhang GROUP BY sales_channel;

    WITH c AS (
      SELECT customer_code,SUM(total_overdue) Overdue
      FROM fact_congno_khachhang GROUP BY customer_code
    ), r AS (
      SELECT *,ROW_NUMBER() OVER(ORDER BY Overdue DESC) rn FROM c WHERE Overdue>0
    )
    SELECT SUM(Overdue) CompanyOverdue,
           SUM(CASE WHEN rn<=10 THEN Overdue ELSE 0 END) Top10Overdue,
           100.0*SUM(CASE WHEN rn<=10 THEN Overdue ELSE 0 END)/NULLIF(SUM(Overdue),0) Top10SharePct
    FROM r;

### S25 — Lịch sử công nợ theo tháng — BLOCKED_HISTORY

    SELECT MIN(snapshot_date) FirstSnapshot,MAX(snapshot_date) LastSnapshot,
           COUNT(DISTINCT snapshot_date) SnapshotCount
    FROM fact_congno_khachhang;

Chỉ được trả chuỗi month-by-month nếu SnapshotCount có đủ các tháng; thiết kế hiện tại đang thay
snapshot cũ bằng snapshot mới.

### S26 — Khách đồng thời giảm mua và nợ xấu — PARTIAL

Chạy trên kho local có attach/mart doanh thu tháng. Nếu chưa có mart doanh thu, dùng S20 xuất danh
sách giảm mua rồi JOIN theo customer_code ngoài SQL.

    SELECT TOP (100) d.customer_code,SUM(d.balance_end) Balance,
           SUM(d.total_overdue) Overdue,r.recent_revenue,r.prior_revenue,
           r.recent_revenue-r.prior_revenue RevenueDelta
    FROM fact_congno_khachhang d
    JOIN mart_customer_revenue_compare r ON r.customer_code=d.customer_code
    GROUP BY d.customer_code,r.recent_revenue,r.prior_revenue
    HAVING SUM(d.total_overdue)>0 AND r.recent_revenue<r.prior_revenue
    ORDER BY SUM(d.total_overdue) DESC;

### S27 — Tồn kho snapshot — READY_CURRENT

    SELECT k.BranchCode,p.Code ItemCode,MAX(p.Name) ProductName,
           SUM(t.Quantity) Quantity,SUM(t.Amount) InventoryValue
    FROM dbo.BRV_TonKhoDK t
    LEFT JOIN dbo.BRV_Kho k ON k.Id=t.WarehouseId
    LEFT JOIN dbo.BRV_SanPham p ON p.Id=t.ItemId
    WHERE t.IsActive=1
    GROUP BY k.BranchCode,p.Code ORDER BY InventoryValue DESC;

### S28 — Lịch sử tồn, cận date và chậm luân chuyển — PARTIAL

    SELECT o.name ObjectName,c.name ColumnName,t.name DataType
    FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
    JOIN sys.types t ON t.user_type_id=c.user_type_id
    WHERE (o.name LIKE '%Kho%' OR o.name LIKE '%Lot%')
      AND (c.name LIKE '%Date%' OR c.name LIKE '%Expiry%' OR c.name LIKE '%Han%')
    ORDER BY o.name,c.column_id;

BRV_TonKhoDK là snapshot, BRV/BRVSX_TonKhoDKLot có lô nhưng catalog chưa có ExpiryDate chuẩn.

### S29 — Hợp đồng/kế hoạch thầu ETC — PARTIAL

    SELECT h.Id0 ContractId,MAX(h.DocNo0) ContractNo,MAX(h.CustomerCode) CustomerCode,
           MAX(h.FromDate0) FromDate,MAX(h.ToDate0) ToDate,
           MAX(h.StatusId) StatusId,SUM(h.AmountBefVat) ContractValue,
           COUNT(DISTINCT h.ItemCode) ContractProducts
    FROM dbo.vHopDongETC h
    GROUP BY h.Id0 ORDER BY ContractValue DESC;

    SELECT o.name ObjectName,c.name ColumnName
    FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
    WHERE o.name LIKE '%Contract%' OR o.name LIKE '%HopDong%' OR o.name LIKE '%TargetETC%'
    ORDER BY o.name,c.column_id;

Chưa được gọi là tỷ lệ trúng thầu nếu chưa map trạng thái tham gia/trúng/thua.

### S30 — KPI theo tháng — READY

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

### S31 — Phân tầng KPI và chuỗi dưới chuẩn — READY

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    ), k AS (
      SELECT EOMONTH(SaveDate) MonthEnd,EmployeeCode,EmployeeName,PositionCode,AreaCode,
             MonthSaleAmount,MonthSaleTarget,MonthSalePercent_R,
             CASE WHEN PositionCode='TDV' THEN 0.65 ELSE 0.70 END Gate
      FROM b WHERE SnapshotRank=1
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
        AND (@ManagerCode IS NULL OR ManagerCode=@ManagerCode)
    )
    SELECT *,CASE WHEN MonthSalePercent_R>=1.2 THEN '>=120%'
                  WHEN MonthSalePercent_R>=1 THEN '100-119%'
                  WHEN MonthSalePercent_R>=0.8 THEN '80-99%'
                  WHEN MonthSalePercent_R>=Gate THEN 'GROUP_GATE'
                  ELSE 'BELOW_GATE' END KPIBand
    FROM k ORDER BY EmployeeCode,MonthEnd;

### S32 — Năng suất nhân sự/đội — PARTIAL

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    )
    SELECT EOMONTH(SaveDate) MonthEnd,AreaCode,ManagerCode,
           COUNT(DISTINCT EmployeeCode) Employees,SUM(MonthSaleAmount) Actual,
           SUM(MonthSaleAmount)/NULLIF(COUNT(DISTINCT EmployeeCode),0) RevenuePerEmployee
    FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
      AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
    GROUP BY EOMONTH(SaveDate),AreaCode,ManagerCode;

Cần FACT_PhatSinhNhanVien được chốt để điều chỉnh chính xác vào/ra/chuyển vùng.

### S33 — Thưởng và hiệu quả thưởng — PARTIAL

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    )
    SELECT EOMONTH(SaveDate) MonthEnd,AreaCode,PositionCode,
           SUM(MonthSaleAmount) Revenue,
           SUM(ISNULL(DMBonus,0)+ISNULL(V15Bonus,0)+ISNULL(V22Bonus,0)
              +ISNULL(V25Bonus,0)+ISNULL(ASOBonus,0)) TotalBonus
    FROM b WHERE SnapshotRank=1
      AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
    GROUP BY EOMONTH(SaveDate),AreaCode,PositionCode;

Chỉ tính bonus/revenue; bonus/profit bị chặn cho tới khi S10 có mapping giá vốn/lợi nhuận.

### S34 — Viếng thăm, tuyến và tỷ lệ có đơn — READY

    WITH v AS (
      SELECT DISTINCT DocDate,EmpDMSCode,CustomerCode
      FROM dbo.DMS_DiTuyen WHERE DocDate>=@FromDate AND DocDate<@ToDate
    ), o AS (
      SELECT DISTINCT DocDate,DMSEmpId1 EmpDMSCode,CustomerCode
      FROM dbo.DMS_DonHangHdr WHERE DocDate>=@FromDate AND DocDate<@ToDate
    )
    SELECT EOMONTH(v.DocDate) MonthEnd,v.EmpDMSCode,COUNT(*) Visits,
           COUNT(DISTINCT v.CustomerCode) VisitedCustomers,
           SUM(CASE WHEN o.CustomerCode IS NOT NULL THEN 1 ELSE 0 END) VisitsWithOrder,
           100.0*SUM(CASE WHEN o.CustomerCode IS NOT NULL THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0) ConversionPct
    FROM v LEFT JOIN o ON o.DocDate=v.DocDate AND o.EmpDMSCode=v.EmpDMSCode
      AND o.CustomerCode=v.CustomerCode
    GROUP BY EOMONTH(v.DocDate),v.EmpDMSCode;

### S35 — Input run-rate/dự báo và mức thiếu target — PARTIAL

    WITH a AS (
      SELECT SUM(Amount9) MTD,COUNT(DISTINCT DocDate) SellingDays
      FROM #sales WHERE DocDate>=@MonthStart AND DocDate<=@AsOfDate
    ), latest AS (
      SELECT EmployeeCode,MAX(SaveDate) d
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=DATEFROMPARTS(YEAR(@AsOfDate),MONTH(@AsOfDate),1) AND SaveDate<=@AsOfDate
      GROUP BY EmployeeCode
    ), t AS (
      SELECT SUM(f.MonthSaleTarget) Target
      FROM dbo.FACT_ThongKeTinhLuong f
      JOIN latest l ON l.EmployeeCode=f.EmployeeCode AND l.d=f.SaveDate
      WHERE f.PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR f.AreaCode=@AreaCode)
        AND (@ManagerCode IS NULL OR f.ManagerCode=@ManagerCode)
    )
    SELECT a.MTD,t.Target,t.Target-a.MTD Gap,
           a.MTD/NULLIF(DAY(@AsOfDate),0)*DAY(EOMONTH(@MonthStart)) LinearRunRate
    FROM a CROSS JOIN t;

Đây chỉ là input/run-rate, không phải forecast xác suất. Forecast chính thức vẫn BLOCKED.

### S36 — Action tracker/chủ sở hữu/deadline — BLOCKED

    SELECT o.name ObjectName,c.name ColumnName
    FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
    WHERE c.name IN ('Owner','OwnerId','Action','ActionStatus','DueDate','Deadline','Commitment')
       OR o.name LIKE '%Action%' OR o.name LIKE '%Task%'
    ORDER BY o.name,c.column_id;

### S37 — Freshness các nguồn — READY

    SELECT 'OTC' Source,MAX(DocDate) BusinessDate,MAX(SyncAt) SyncAt FROM dbo.vHoaDonTotal
    UNION ALL SELECT 'ETC',MAX(DocDate),MAX(SyncAt) FROM dbo.vHoaDonETCTotal
    UNION ALL SELECT 'KPI_CUSTOMER',MAX(SaveDate),MAX(CreatedAt) FROM dbo.FACT_TongHopKhachHang
    UNION ALL SELECT 'KPI_SALARY',MAX(SaveDate),MAX(CreatedAt) FROM dbo.FACT_ThongKeTinhLuong
    UNION ALL SELECT 'PROMOTION',MAX(h.DocDate),MAX(x.SyncAt)
      FROM dbo.DMS_DonHangCTKM x LEFT JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId;

### S38 — Chất lượng mapping, target và snapshot — READY

    WITH snaps AS (
      SELECT EOMONTH(SaveDate) MonthEnd,MAX(SaveDate) SaveDate
      FROM dbo.FACT_TongHopKhachHang
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate GROUP BY EOMONTH(SaveDate)
    )
    SELECT EOMONTH(f.SaveDate) MonthEnd,
      COUNT(DISTINCT f.EmployeeCode) Employees,
      COUNT(DISTINCT CASE WHEN f.ManagerCode IS NULL OR f.ManagerCode='' THEN f.EmployeeCode END) MissingManager,
      COUNT(DISTINCT CASE WHEN f.MonthSaleTarget IS NULL OR f.MonthSaleTarget<=0 THEN f.EmployeeCode END) MissingTarget,
      COUNT(DISTINCT CASE WHEN n.EmployeeCode IS NULL THEN f.EmployeeCode END) MissingEmployeeDim
    FROM dbo.FACT_TongHopKhachHang f
    LEFT JOIN dbo.DIM_NhanVien n ON n.EmployeeCode=f.EmployeeCode
      AND ISNULL(n.IsDuplicate,0)=0
    JOIN snaps s ON s.SaveDate=f.SaveDate
    GROUP BY EOMONTH(f.SaveDate);

### S39 — Hiệu suất nhân viên/đội theo tháng — READY

    WITH snaps AS (
      SELECT EOMONTH(SaveDate) MonthEnd,MAX(SaveDate) SaveDate
      FROM dbo.FACT_TongHopKhachHang
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate GROUP BY EOMONTH(SaveDate)
    ), e AS (
      SELECT EOMONTH(f.SaveDate) MonthEnd,f.EmployeeCode,MAX(f.ManagerCode) ManagerCode,
             SUM(f.Amount_CT) Actual,MAX(f.MonthSaleTarget) Target,
             COUNT(DISTINCT f.CustomerCode) Customers
      FROM dbo.FACT_TongHopKhachHang f JOIN snaps s ON s.SaveDate=f.SaveDate
      WHERE 1=1
        AND (@ManagerCode IS NULL OR f.ManagerCode=@ManagerCode)
      GROUP BY EOMONTH(f.SaveDate),f.EmployeeCode
    )
    SELECT *,100.0*Actual/NULLIF(Target,0) AchievementPct,
           Actual-LAG(Actual) OVER(PARTITION BY EmployeeCode ORDER BY MonthEnd) MoMDelta
    FROM e ORDER BY EmployeeCode,MonthEnd;

### S40 — Khách ngừng mua/im lặng — READY

    WITH c AS (
      SELECT CustomerCode,MAX(DocDate) LastPurchaseDate,
             SUM(CASE WHEN DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthStart
                      THEN Amount9 ELSE 0 END) Prior3M,
             SUM(CASE WHEN DocDate>=@MonthStart AND DocDate<@MonthEnd THEN Amount9 ELSE 0 END) Cur
      FROM #sales GROUP BY CustomerCode
    )
    SELECT TOP (200) *,DATEDIFF(day,LastPurchaseDate,@AsOfDate) SilentDays
    FROM c WHERE Cur=0 AND Prior3M>0 ORDER BY Prior3M DESC;

### S41 — Cơ hội bán chéo — DERIVED

    WITH l AS (
      SELECT DISTINCT OrderKey,CustomerCode,ItemCode FROM #sales
      WHERE DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthEnd AND UnitPrice>0
    ), pairs AS (
      SELECT TOP (50) a.ItemCode A,b.ItemCode B,COUNT(*) Together
      FROM l a JOIN l b ON b.OrderKey=a.OrderKey AND b.ItemCode>a.ItemCode
      GROUP BY a.ItemCode,b.ItemCode ORDER BY COUNT(*) DESC
    )
    SELECT p.A,p.B,p.Together,
           COUNT(DISTINCT l.CustomerCode) CandidatesBuyAOnly
    FROM pairs p JOIN l ON l.ItemCode=p.A
    WHERE NOT EXISTS(SELECT 1 FROM l x WHERE x.CustomerCode=l.CustomerCode AND x.ItemCode=p.B)
    GROUP BY p.A,p.B,p.Together
    ORDER BY p.Together DESC;

Danh sách khách ứng viên của từng cặp, chỉ trong 20 cặp mạnh nhất, xếp theo doanh thu khách:

    WITH l AS (
      SELECT DISTINCT OrderKey,CustomerCode,ItemCode FROM #sales
      WHERE DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthEnd AND UnitPrice>0
    ), pairs AS (
      SELECT TOP (20) a.ItemCode A,b.ItemCode B,COUNT(*) Together
      FROM l a JOIN l b ON b.OrderKey=a.OrderKey AND b.ItemCode>a.ItemCode
      GROUP BY a.ItemCode,b.ItemCode ORDER BY COUNT(*) DESC
    ), ck AS (
      SELECT DISTINCT CustomerCode,ItemCode FROM l
    ), rev AS (
      SELECT CustomerCode,SUM(Amount9) Revenue3M FROM #sales
      WHERE DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthEnd
      GROUP BY CustomerCode
    ), owner_date AS (
      SELECT CustomerCode,MAX(DocDate) d FROM #sales
      WHERE DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthEnd
      GROUP BY CustomerCode
    ), owner AS (
      SELECT s.CustomerCode,MAX(s.EmpDMSCode) EmpDMSCode
      FROM #sales s JOIN owner_date d ON d.CustomerCode=s.CustomerCode AND d.d=s.DocDate
      GROUP BY s.CustomerCode
    )
    SELECT TOP (500) p.A,p.B,p.Together,x.CustomerCode,
           n.EmployeeCode,n.Name EmployeeName,r.Revenue3M
    FROM pairs p JOIN ck x ON x.ItemCode=p.A
    LEFT JOIN rev r ON r.CustomerCode=x.CustomerCode
    LEFT JOIN owner o ON o.CustomerCode=x.CustomerCode
    OUTER APPLY (SELECT TOP (1) d.EmployeeCode,d.Name FROM dbo.DIM_NhanVien d
                 WHERE d.DMSId=o.EmpDMSCode ORDER BY ISNULL(d.IsDuplicate,0),d.EmployeeCode) n
    WHERE NOT EXISTS(SELECT 1 FROM ck y WHERE y.CustomerCode=x.CustomerCode AND y.ItemCode=p.B)
    ORDER BY r.Revenue3M DESC,p.Together DESC;

Tách hai tầng cặp/khách như S74. Bản chạy 28/08/2026 ghép chung ra 171.106 dòng vì mỗi cặp bị nhân
bản một lần cho từng khách ứng viên.

### S42 — Đơn hủy/chậm/chưa hóa đơn — READY

    SELECT TOP (200) h.Id OrderId,h.DocDate,h.CustomerCode,h.DMSEmpId1,
           h.StatusId,h.StatusDescription,h.IsSync,MIN(v.DocDate) InvoiceDate,
           DATEDIFF(day,h.DocDate,MIN(v.DocDate)) LagDays
    FROM dbo.DMS_DonHangHdr h
    LEFT JOIN dbo.vHoaDonTotal v ON TRY_CONVERT(int,v.DMSId)=h.Id
    WHERE h.DocDate>=@MonthStart AND h.DocDate<@MonthEnd
    GROUP BY h.Id,h.DocDate,h.CustomerCode,h.DMSEmpId1,h.StatusId,h.StatusDescription,h.IsSync
    HAVING MIN(v.DocDate) IS NULL OR ABS(DATEDIFF(day,h.DocDate,MIN(v.DocDate)))>=2;

### S43 — Gap target theo đội/cá nhân — PARTIAL

    WITH latest43 AS (
      SELECT EmployeeCode,MAX(SaveDate) d
      FROM dbo.FACT_TongHopKhachHang
      WHERE SaveDate>=DATEFROMPARTS(YEAR(@AsOfDate),MONTH(@AsOfDate),1) AND SaveDate<=@AsOfDate
      GROUP BY EmployeeCode
    ), e AS (
      SELECT f.EmployeeCode,MAX(f.ManagerCode) ManagerCode,
             SUM(f.Amount_CT) Actual,MAX(f.MonthSaleTarget) Target
      FROM dbo.FACT_TongHopKhachHang f
      JOIN latest43 l ON l.EmployeeCode=f.EmployeeCode AND l.d=f.SaveDate
      WHERE (@ManagerCode IS NULL OR f.ManagerCode=@ManagerCode)
      GROUP BY f.EmployeeCode
    )
    SELECT ManagerCode,EmployeeCode,Actual,Target,Actual-Target Gap,
           100.0*Actual/NULLIF(Target,0) AchievementPct,
           0.65*Target-Actual Gap65,0.80*Target-Actual Gap80,
           1.00*Target-Actual Gap100,1.20*Target-Actual Gap120
    FROM e ORDER BY AchievementPct;

### S44 — Hiệu suất khách hàng theo nhân viên — READY

    WITH snaps AS (
      SELECT EOMONTH(SaveDate) MonthEnd,MAX(SaveDate) SaveDate
      FROM dbo.FACT_TongHopKhachHang
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate GROUP BY EOMONTH(SaveDate)
    ), x AS (
      SELECT EOMONTH(f.SaveDate) MonthEnd,f.EmployeeCode,f.ManagerCode,
             COUNT(DISTINCT f.CustomerCode) AssignedCustomers,
             COUNT(DISTINCT CASE WHEN f.IsAC=1 THEN f.CustomerCode END) ActiveCustomers,
             COUNT(DISTINCT CASE WHEN f.IsNC=1 THEN f.CustomerCode END) NewCustomers,
             COUNT(DISTINCT CASE WHEN f.IsRO=1 THEN f.CustomerCode END) ReorderCustomers,
             SUM(f.Amount_CT) Revenue
      FROM dbo.FACT_TongHopKhachHang f JOIN snaps s ON s.SaveDate=f.SaveDate
      WHERE 1=1
        AND (@ManagerCode IS NULL OR f.ManagerCode=@ManagerCode)
      GROUP BY EOMONTH(f.SaveDate),f.EmployeeCode,f.ManagerCode
    )
    SELECT *,Revenue/NULLIF(ActiveCustomers,0) RevenuePerActiveCustomer
    FROM x ORDER BY MonthEnd,Revenue DESC;

### S45 — Thu tiền, DSO và cam kết thu — BLOCKED_HISTORY

    SELECT o.name ObjectName,c.name ColumnName
    FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
    WHERE o.schema_id=SCHEMA_ID('dbo')
      AND (o.name LIKE '%HTT%' OR o.name LIKE '%ThuTien%' OR o.name LIKE '%CongNo%')
      AND (c.name LIKE '%Paid%' OR c.name LIKE '%Amount%' OR c.name LIKE '%Date%'
        OR c.name LIKE '%Due%' OR c.name LIKE '%Promise%' OR c.name LIKE '%Commit%')
    ORDER BY o.name,c.column_id;

Phải map chứng từ thu tiền theo hóa đơn/khách và lưu snapshot tháng trước khi tính DSO/roll-rate.

### S46 — Target sản phẩm/SKU — PARTIAL

    WITH snaps AS (
      SELECT EOMONTH(SaveDate) MonthEnd,MAX(SaveDate) SaveDate
      FROM dbo.FACT_TongHopSanPham
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate GROUP BY EOMONTH(SaveDate)
    )
    SELECT EOMONTH(f.SaveDate) MonthEnd,f.AreaCode,
           COUNT(DISTINCT f.ItemCode) Items,
           COUNT(DISTINCT CASE WHEN f.IsTargetProduct=1 THEN f.ItemCode END) TargetItems,
           COUNT(DISTINCT f.EmployeeCode) Employees,
           COUNT(DISTINCT CASE WHEN f.IsTargetProduct=1 THEN f.EmployeeCode END) EmployeesWithTarget
    FROM dbo.FACT_TongHopSanPham f JOIN snaps s ON s.SaveDate=f.SaveDate
    WHERE (@AreaCode IS NULL OR f.AreaCode=@AreaCode)
      AND (@ManagerCode IS NULL OR f.ManagerCode=@ManagerCode)
    GROUP BY EOMONTH(f.SaveDate),f.AreaCode
    ORDER BY MonthEnd,f.AreaCode;

Độ phủ SKU trọng tâm theo từng TDV, xếp theo mức phủ thấp nhất:

    WITH snaps46 AS (
      SELECT EOMONTH(SaveDate) MonthEnd,MAX(SaveDate) SaveDate
      FROM dbo.FACT_TongHopSanPham
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate GROUP BY EOMONTH(SaveDate)
    )
    SELECT TOP (300) EOMONTH(f.SaveDate) MonthEnd,f.AreaCode,f.ManagerCode,f.EmployeeCode,
           COUNT(DISTINCT CASE WHEN f.IsTargetProduct=1 THEN f.ItemCode END) TargetItemsSold,
           COUNT(DISTINCT f.ItemCode) ItemsSold
    FROM dbo.FACT_TongHopSanPham f JOIN snaps46 s ON s.SaveDate=f.SaveDate
    WHERE (@AreaCode IS NULL OR f.AreaCode=@AreaCode)
      AND (@ManagerCode IS NULL OR f.ManagerCode=@ManagerCode)
    GROUP BY EOMONTH(f.SaveDate),f.AreaCode,f.ManagerCode,f.EmployeeCode
    ORDER BY MonthEnd DESC,TargetItemsSold;

Trước đây gom tới mức tháng × vùng × QLV × TDV × nhóm × SKU nên ra 66.809 dòng — đúng dữ liệu nhưng
không phải đáp án. Nay tổng hợp đúng hai cấp mà câu hỏi hỏi: vùng (M32) và TDV (V30). Vẫn PARTIAL vì
chưa map được cột giá trị/sản lượng target nên không tính được % hoàn thành.

Catalog có cờ sản phẩm trọng tâm nhưng cần map cột giá trị/sản lượng target trước khi tính % hoàn thành.

### S47 — Thiếu hàng và doanh số có nguy cơ mất — DERIVED

    WITH demand AS (
      SELECT ItemCode,SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END)/3.0 AvgMonthlyQty,
             SUM(Amount9)/3.0 AvgMonthlyRevenue
      FROM #sales WHERE DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthStart
      GROUP BY ItemCode
    ), stock AS (
      SELECT p.Code ItemCode,SUM(t.Quantity) StockQty
      FROM dbo.BRV_TonKhoDK t JOIN dbo.BRV_SanPham p ON p.Id=t.ItemId
      WHERE t.IsActive=1 GROUP BY p.Code
    )
    SELECT d.ItemCode,s.StockQty,d.AvgMonthlyQty,d.AvgMonthlyRevenue,
           s.StockQty/NULLIF(d.AvgMonthlyQty,0) MonthsOfCover
    FROM demand d LEFT JOIN stock s ON s.ItemCode=d.ItemCode
    WHERE ISNULL(s.StockQty,0)<d.AvgMonthlyQty ORDER BY MonthsOfCover;

### S48 — Danh sách khách ưu tiên hành động — DERIVED

    WITH c AS (
      SELECT CustomerCode,MAX(DocDate) LastPurchaseDate,
        SUM(CASE WHEN DocDate>=@MonthStart AND DocDate<@MonthEnd THEN Amount9 ELSE 0 END) Cur,
        SUM(CASE WHEN DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthStart THEN Amount9 ELSE 0 END) Prior3M
      FROM #sales GROUP BY CustomerCode
    )
    SELECT TOP (100) CustomerCode,LastPurchaseDate,Cur,Prior3M,
      CASE WHEN Cur=0 AND Prior3M>0 THEN 'REACTIVATE'
           WHEN Cur<Prior3M/3.0 THEN 'RETAIN'
           WHEN Cur>Prior3M/3.0 THEN 'EXPAND' ELSE 'REVIEW' END PriorityAction
    FROM c ORDER BY ABS(Cur-Prior3M/3.0) DESC;

### S49 — Streak tăng/giảm liên tiếp theo địa bàn — READY

Cho câu hỏi "đơn vị nào tăng/giảm liên tục 3/6 tháng". Trả về THẲNG số tháng liên tiếp, không bắt
người đọc tự đếm từ bảng MoM.

    WITH m AS (
      SELECT EOMONTH(DocDate) MonthEnd,AreaCode,SUM(Amount9) Revenue
      FROM #sales GROUP BY EOMONTH(DocDate),AreaCode
    ), d AS (
      SELECT MonthEnd,AreaCode,Revenue,
             CASE WHEN Revenue>LAG(Revenue) OVER(PARTITION BY AreaCode ORDER BY MonthEnd) THEN 1
                  WHEN Revenue<LAG(Revenue) OVER(PARTITION BY AreaCode ORDER BY MonthEnd) THEN -1
                  ELSE 0 END Dir
      FROM m
    ), g AS (
      SELECT *,ROW_NUMBER() OVER(PARTITION BY AreaCode ORDER BY MonthEnd)
               -ROW_NUMBER() OVER(PARTITION BY AreaCode,Dir ORDER BY MonthEnd) Grp
      FROM d WHERE Dir<>0
    ), streak AS (
      SELECT AreaCode,Dir,COUNT(*) StreakMonths,MAX(MonthEnd) LastMonth
      FROM g GROUP BY AreaCode,Dir,Grp
    )
    SELECT AreaCode,CASE WHEN Dir=1 THEN 'TANG' ELSE 'GIAM' END Direction,
           StreakMonths,LastMonth
    FROM streak WHERE StreakMonths>=3
    ORDER BY Direction,StreakMonths DESC,AreaCode;

### S50 — Quy mô so tăng trưởng theo địa bàn — READY

Cho câu hỏi "quy mô lớn nhưng tăng trưởng thấp / quy mô nhỏ nhưng tăng nhanh". Trả về sẵn nhãn
phân nhóm thay vì để người đọc tự đối chiếu hai cột.

    WITH m AS (
      SELECT EOMONTH(DocDate) MonthEnd,AreaCode,CityName,SUM(Amount9) Revenue
      FROM #sales GROUP BY EOMONTH(DocDate),AreaCode,CityName
    ), cur AS (
      SELECT AreaCode,CityName,SUM(Revenue) Revenue3M
      FROM m WHERE MonthEnd>DATEADD(month,-3,EOMONTH(@AsOfDate))
      GROUP BY AreaCode,CityName
    ), pre AS (
      SELECT AreaCode,CityName,SUM(Revenue) RevenuePrev3M
      FROM m WHERE MonthEnd>DATEADD(month,-6,EOMONTH(@AsOfDate))
        AND MonthEnd<=DATEADD(month,-3,EOMONTH(@AsOfDate))
      GROUP BY AreaCode,CityName
    ), j AS (
      SELECT c.AreaCode,c.CityName,c.Revenue3M,ISNULL(p.RevenuePrev3M,0) RevenuePrev3M,
             100.0*(c.Revenue3M-ISNULL(p.RevenuePrev3M,0))/NULLIF(p.RevenuePrev3M,0) GrowthPct
      FROM cur c LEFT JOIN pre p ON p.AreaCode=c.AreaCode AND p.CityName=c.CityName
    )
    SELECT *,NTILE(4) OVER(ORDER BY Revenue3M DESC) SizeQuartile,
           CASE WHEN NTILE(4) OVER(ORDER BY Revenue3M DESC)=1 AND ISNULL(GrowthPct,0)<5
                     THEN 'QUY_MO_LON_TANG_THAP'
                WHEN NTILE(4) OVER(ORDER BY Revenue3M DESC)=4 AND ISNULL(GrowthPct,0)>15
                     THEN 'QUY_MO_NHO_TANG_NHANH'
                ELSE 'BINH_THUONG' END Nhom
    FROM j ORDER BY Revenue3M DESC;

### S51 — Độ phủ khách hàng theo địa bàn so chuẩn miền — READY

Cho câu hỏi "địa bàn nào độ phủ khách thấp so với địa bàn tương đồng". "Tương đồng" định nghĩa là
CÙNG MIỀN — so với trung vị của miền đó, không so toàn quốc.

    WITH c AS (
      SELECT AreaCode,CityName,COUNT(DISTINCT CustomerCode) ActiveCustomers,
             SUM(Amount9) Revenue
      FROM #sales WHERE DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthEnd
      GROUP BY AreaCode,CityName
    ), med AS (
      SELECT AreaCode,
             PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY ActiveCustomers)
               OVER(PARTITION BY AreaCode) MedianCustomers,
             PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY Revenue)
               OVER(PARTITION BY AreaCode) MedianRevenue
      FROM c
    ), m1 AS (SELECT DISTINCT AreaCode,MedianCustomers,MedianRevenue FROM med)
    SELECT c.AreaCode,c.CityName,c.ActiveCustomers,m1.MedianCustomers,
           c.Revenue,m1.MedianRevenue,
           CASE WHEN c.ActiveCustomers<0.6*m1.MedianCustomers THEN 'DO_PHU_THAP' ELSE 'DAT' END CoverageFlag
    FROM c JOIN m1 ON m1.AreaCode=c.AreaCode
    ORDER BY c.AreaCode,c.ActiveCustomers;

### S52 — Địa bàn kéo giảm kết quả — READY

Cho câu hỏi "tỉnh/chi nhánh/NPP nào đang kéo giảm kết quả". Xếp theo mức ĐÓNG GÓP ÂM tuyệt đối,
không phải theo % giảm — một tỉnh nhỏ giảm 50% ít quan trọng hơn tỉnh lớn giảm 5%.

Lưu ý: cột BranchCode/DistributorCode chỉ dùng được nếu bước kiểm cột ở mục 2 xác nhận có thật trên
vHoaDonTotal/vHoaDonETCTotal. Nếu thiếu, bỏ hai cột đó khỏi GROUP BY và đánh dấu câu M10 là BLOCKED
phần chi nhánh/NPP.

    WITH m AS (
      SELECT EOMONTH(DocDate) MonthEnd,AreaCode,CityName,SUM(Amount9) Revenue
      FROM #sales GROUP BY EOMONTH(DocDate),AreaCode,CityName
    ), d AS (
      SELECT MonthEnd,AreaCode,CityName,Revenue,
             Revenue-LAG(Revenue) OVER(PARTITION BY AreaCode,CityName ORDER BY MonthEnd) MoMDelta
      FROM m
    ), tot AS (
      SELECT MonthEnd,SUM(Revenue) TotalRevenue,
             SUM(Revenue)-LAG(SUM(Revenue)) OVER(ORDER BY MonthEnd) TotalDelta
      FROM m GROUP BY MonthEnd
    )
    SELECT d.MonthEnd,d.AreaCode,d.CityName,d.Revenue,d.MoMDelta,
           t.TotalDelta,
           100.0*d.MoMDelta/NULLIF(ABS(t.TotalDelta),0) ContributionPctOfChange
    FROM d JOIN tot t ON t.MonthEnd=d.MonthEnd
    WHERE d.MoMDelta<0 AND d.MonthEnd=EOMONTH(@MonthStart)
    ORDER BY d.MoMDelta;

### S53 — Địa bàn dưới chuẩn miền về khách, đơn và doanh thu/khách — READY

Cho câu hỏi "tỉnh/huyện nào ít khách hoạt động, ít đơn hoặc doanh thu/khách thấp hơn chuẩn miền".
Khác S51 ở chỗ so đủ BA chỉ số, không chỉ độ phủ khách.

Số đơn dùng khóa Channel + Stt qua OrderKey (nguyên tắc pass/fail số 4).

    WITH c AS (
      SELECT AreaCode,CityName,
             COUNT(DISTINCT CustomerCode) ActiveCustomers,
             COUNT(DISTINCT OrderKey) Orders,
             SUM(Amount9) Revenue
      FROM #sales WHERE DocDate>=@MonthStart AND DocDate<@MonthEnd
      GROUP BY AreaCode,CityName
    ), s AS (
      SELECT *,Revenue/NULLIF(ActiveCustomers,0) RevenuePerCustomer,
             Orders*1.0/NULLIF(ActiveCustomers,0) OrdersPerCustomer
      FROM c
    ), b AS (
      SELECT AreaCode,AVG(RevenuePerCustomer) AvgRevPerCus,AVG(OrdersPerCustomer) AvgOrdPerCus,
             AVG(ActiveCustomers*1.0) AvgCustomers
      FROM s GROUP BY AreaCode
    )
    , q AS (
      SELECT s.*,b.AvgRevPerCus,b.AvgOrdPerCus,b.AvgCustomers,
             CASE WHEN s.ActiveCustomers<b.AvgCustomers THEN 1 ELSE 0 END FlagItKhach,
             CASE WHEN s.OrdersPerCustomer<b.AvgOrdPerCus THEN 1 ELSE 0 END FlagItDon,
             CASE WHEN s.RevenuePerCustomer<b.AvgRevPerCus THEN 1 ELSE 0 END FlagDoanhThuThap
      FROM s JOIN b ON b.AreaCode=s.AreaCode
    )
    SELECT * FROM q
    ORDER BY FlagItKhach+FlagItDon+FlagDoanhThuThap DESC,Revenue;

### S54 — Đội phụ thuộc ít nhân viên hoặc ít khách — READY

Cho câu hỏi "đội nào doanh thu cao nhưng phụ thuộc vào ít nhân viên/ít khách". Đo bằng tỷ trọng
người/khách đứng đầu, không phải bằng số đếm đơn thuần.

Gộp snapshot theo từng nhân viên trong tháng (xem quy ước ở mục 1).

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    ), e AS (
      SELECT EOMONTH(SaveDate) MonthEnd,ManagerCode,EmployeeCode,MonthSaleAmount
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
    ), t AS (
      SELECT MonthEnd,ManagerCode,SUM(MonthSaleAmount) TeamRevenue,
             COUNT(DISTINCT EmployeeCode) Employees,
             MAX(MonthSaleAmount) TopEmployeeRevenue
      FROM e GROUP BY MonthEnd,ManagerCode
    )
    SELECT MonthEnd,ManagerCode,TeamRevenue,Employees,TopEmployeeRevenue,
           100.0*TopEmployeeRevenue/NULLIF(TeamRevenue,0) TopEmployeeSharePct,
           CASE WHEN 100.0*TopEmployeeRevenue/NULLIF(TeamRevenue,0)>40 THEN 'PHU_THUOC_CAO'
                ELSE 'PHAN_TAN' END DependencyFlag
    FROM t ORDER BY TopEmployeeSharePct DESC;

### S55 — Nhân viên giảm liên tiếp và nguyên nhân — READY

Cho câu hỏi "nhân viên nào giảm liên tiếp 2–3 tháng; do mất khách, ít đơn hay giảm giá trị đơn".
Ghép streak (từ bảng lương) với ba chỉ số nguyên nhân (từ hóa đơn) trong cùng một kết quả.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    ), e AS (
      SELECT EOMONTH(SaveDate) MonthEnd,EmployeeCode,EmployeeName,ManagerCode,MonthSaleAmount
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@ManagerCode IS NULL OR ManagerCode=@ManagerCode)
    ), d AS (
      SELECT *,CASE WHEN MonthSaleAmount<LAG(MonthSaleAmount)
                      OVER(PARTITION BY EmployeeCode ORDER BY MonthEnd) THEN 1 ELSE 0 END IsDown
      FROM e
    ), g AS (
      SELECT *,ROW_NUMBER() OVER(PARTITION BY EmployeeCode ORDER BY MonthEnd)
               -ROW_NUMBER() OVER(PARTITION BY EmployeeCode,IsDown ORDER BY MonthEnd) Grp
      FROM d WHERE IsDown=1
    ), streak AS (
      SELECT EmployeeCode,MAX(EmployeeName) EmployeeName,MAX(ManagerCode) ManagerCode,
             COUNT(*) DownMonths,MAX(MonthEnd) LastMonth
      FROM g GROUP BY EmployeeCode,Grp
    ), cause AS (
      SELECT EmpDMSCode,EOMONTH(DocDate) MonthEnd,
             COUNT(DISTINCT CustomerCode) Customers,COUNT(DISTINCT OrderKey) Orders,
             SUM(Amount9)/NULLIF(COUNT(DISTINCT OrderKey),0) AOV,
             COUNT(DISTINCT ItemCode) SKUs
      FROM #sales GROUP BY EmpDMSCode,EOMONTH(DocDate)
    )
    SELECT s.EmployeeCode,s.EmployeeName,s.ManagerCode,s.DownMonths,s.LastMonth,
           c.Customers,c.Orders,c.AOV,c.SKUs,
           c.Customers-LAG(c.Customers) OVER(PARTITION BY s.EmployeeCode ORDER BY c.MonthEnd) CustomerDelta,
           c.Orders-LAG(c.Orders) OVER(PARTITION BY s.EmployeeCode ORDER BY c.MonthEnd) OrderDelta,
           c.AOV-LAG(c.AOV) OVER(PARTITION BY s.EmployeeCode ORDER BY c.MonthEnd) AOVDelta
    FROM streak s
    LEFT JOIN dbo.DIM_NhanVien n ON n.EmployeeCode=s.EmployeeCode
    LEFT JOIN cause c ON c.EmpDMSCode=n.DMSId AND c.MonthEnd=s.LastMonth
    WHERE s.DownMonths>=2
    ORDER BY s.DownMonths DESC,s.EmployeeCode;

### S56 — Doanh số, target và xu hướng từng TDV theo tháng — READY

Cho câu hỏi "doanh số, target, % hoàn thành từng TDV theo tháng; xếp hạng và xu hướng 3/6 tháng".
Khác S39 (tổng hợp theo đội) ở chỗ giữ nguyên TỪNG NHÂN VIÊN qua các tháng, kèm thứ hạng và trung
bình trượt.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    ), e AS (
      SELECT EOMONTH(SaveDate) MonthEnd,EmployeeCode,EmployeeName,ManagerCode,AreaCode,
             MonthSaleAmount Actual,MonthSaleTarget Target
      FROM b WHERE SnapshotRank=1 AND PositionCode='TDV'
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
        AND (@ManagerCode IS NULL OR ManagerCode=@ManagerCode)
    )
    SELECT MonthEnd,EmployeeCode,EmployeeName,ManagerCode,AreaCode,Actual,Target,
           100.0*Actual/NULLIF(Target,0) AchievementPct,
           DENSE_RANK() OVER(PARTITION BY MonthEnd ORDER BY Actual DESC) RankInMonth,
           AVG(Actual) OVER(PARTITION BY EmployeeCode ORDER BY MonthEnd
                            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) Rolling3M,
           AVG(Actual) OVER(PARTITION BY EmployeeCode ORDER BY MonthEnd
                            ROWS BETWEEN 5 PRECEDING AND CURRENT ROW) Rolling6M
    FROM e ORDER BY EmployeeCode,MonthEnd;

### S57 — Đóng góp của nhân viên vào tăng/giảm doanh số đội — READY

Cho câu hỏi "nhân viên nào đóng góp nhiều nhất vào tăng/giảm doanh số đội tháng này". Trả về mức
đóng góp tuyệt đối VÀ tỷ trọng trong biến động của đội.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    ), e AS (
      SELECT EOMONTH(SaveDate) MonthEnd,EmployeeCode,EmployeeName,ManagerCode,MonthSaleAmount
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@ManagerCode IS NULL OR ManagerCode=@ManagerCode)
    ), d AS (
      SELECT *,MonthSaleAmount-LAG(MonthSaleAmount)
                 OVER(PARTITION BY EmployeeCode ORDER BY MonthEnd) EmpDelta
      FROM e
    ), team AS (
      SELECT MonthEnd,ManagerCode,SUM(EmpDelta) TeamDelta
      FROM d GROUP BY MonthEnd,ManagerCode
    )
    SELECT d.MonthEnd,d.ManagerCode,d.EmployeeCode,d.EmployeeName,
           d.MonthSaleAmount,d.EmpDelta,t.TeamDelta,
           100.0*d.EmpDelta/NULLIF(ABS(t.TeamDelta),0) ContributionPct
    FROM d JOIN team t ON t.MonthEnd=d.MonthEnd AND t.ManagerCode=d.ManagerCode
    WHERE d.MonthEnd=EOMONTH(@MonthStart) AND d.EmpDelta IS NOT NULL
    ORDER BY ABS(d.EmpDelta) DESC;

### S58 — Vùng dưới kế hoạch liên tiếp và hụt tích lũy — PARTIAL

Cho câu hỏi "vùng nào dưới 80% kế hoạch liên tiếp; tổng hụt tích lũy bao nhiêu". Khác S43 (gap tại
một kỳ) ở chỗ đếm SỐ THÁNG LIÊN TIẾP và CỘNG DỒN phần hụt qua các tháng đó.

Target ETC toàn kênh chưa map riêng nên phần ETC vẫn PARTIAL — xem ghi chú ở S02.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    ), k AS (
      SELECT EOMONTH(SaveDate) MonthEnd,AreaCode,
             SUM(MonthSaleAmount) Actual,SUM(MonthSaleTarget) Target
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
      GROUP BY EOMONTH(SaveDate),AreaCode
    ), f AS (
      SELECT *,100.0*Actual/NULLIF(Target,0) Pct,
             CASE WHEN 100.0*Actual/NULLIF(Target,0)<80 THEN 1 ELSE 0 END Below
      FROM k
    ), g AS (
      SELECT *,ROW_NUMBER() OVER(PARTITION BY AreaCode ORDER BY MonthEnd)
               -ROW_NUMBER() OVER(PARTITION BY AreaCode,Below ORDER BY MonthEnd) Grp
      FROM f WHERE Below=1
    )
    SELECT AreaCode,COUNT(*) MonthsBelow80,MIN(MonthEnd) FromMonth,MAX(MonthEnd) ToMonth,
           SUM(Target-Actual) CumulativeGap,AVG(Pct) AvgPct
    FROM g GROUP BY AreaCode,Grp
    HAVING COUNT(*)>=2
    ORDER BY CumulativeGap DESC;

### S59 — Mức cần đạt các mốc 65/80/100/120% và nhịp ngày còn lại — PARTIAL

Cho câu hỏi "còn thiếu bao nhiêu để đạt 65/70, 80, 100, 120%; mỗi ngày còn lại cần bán bao nhiêu".
Khác S43 ở chỗ tính thêm NHỊP NGÀY CÒN LẠI, không chỉ khoảng hụt.

Ngưỡng gate 65% cho TDV và 70% cho quản lý — xem S31.

    WITH latest59 AS (
      SELECT EmployeeCode,MAX(SaveDate) d
      FROM dbo.FACT_TongHopKhachHang
      WHERE SaveDate>=DATEFROMPARTS(YEAR(@AsOfDate),MONTH(@AsOfDate),1) AND SaveDate<=@AsOfDate
      GROUP BY EmployeeCode
    ), e AS (
      SELECT f.EmployeeCode,MAX(f.ManagerCode) ManagerCode,
             SUM(f.Amount_CT) Actual,MAX(f.MonthSaleTarget) Target
      FROM dbo.FACT_TongHopKhachHang f
      JOIN latest59 l ON l.EmployeeCode=f.EmployeeCode AND l.d=f.SaveDate
      WHERE (@ManagerCode IS NULL OR f.ManagerCode=@ManagerCode)
        AND (@EmployeeCode IS NULL OR f.EmployeeCode=@EmployeeCode)
      GROUP BY f.EmployeeCode
    ), r AS (
      SELECT *,DAY(EOMONTH(@MonthStart))-DAY(@AsOfDate) DaysLeft FROM e
    )
    SELECT ManagerCode,EmployeeCode,Actual,Target,DaysLeft,
           0.65*Target-Actual Gap65,0.80*Target-Actual Gap80,
           1.00*Target-Actual Gap100,1.20*Target-Actual Gap120,
           (0.80*Target-Actual)/NULLIF(DaysLeft,0) PerDayTo80,
           (1.00*Target-Actual)/NULLIF(DaysLeft,0) PerDayTo100
    FROM r ORDER BY Gap100 DESC;

### S60 — Địa bàn con dưới kế hoạch và TDV phụ trách — PARTIAL

Cho câu hỏi "tỉnh/địa bàn con nào dưới kế hoạch; hụt bao nhiêu và TDV nào phụ trách". Nối doanh thu
theo tỉnh (hóa đơn) với target theo nhân viên (bảng lương) qua DMSId.

Target theo tỉnh không có sẵn; phần hụt quy về nhân viên phụ trách tỉnh đó nên vẫn PARTIAL.

    WITH s AS (
      SELECT CityName,AreaCode,EmpDMSCode,SUM(Amount9) Revenue,
             COUNT(DISTINCT CustomerCode) Customers
      FROM #sales WHERE DocDate>=@MonthStart AND DocDate<@MonthEnd
      GROUP BY CityName,AreaCode,EmpDMSCode
    ), b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@MonthStart AND SaveDate<@MonthEnd
    ), t AS (
      SELECT EmployeeCode,MonthSaleTarget Target,MonthSaleAmount Actual,ManagerCode
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@ManagerCode IS NULL OR ManagerCode=@ManagerCode)
    )
    SELECT s.AreaCode,s.CityName,n.EmployeeCode,n.Name EmployeeName,t.ManagerCode,
           s.Revenue,s.Customers,t.Target,t.Actual,
           100.0*t.Actual/NULLIF(t.Target,0) AchievementPct,
           t.Target-t.Actual Gap
    FROM s
    LEFT JOIN dbo.DIM_NhanVien n ON n.DMSId=s.EmpDMSCode
    LEFT JOIN t ON t.EmployeeCode=n.EmployeeCode
    WHERE 100.0*t.Actual/NULLIF(t.Target,0)<100
    ORDER BY Gap DESC;

### S61 — Hiệu quả mở khách mới so tỷ lệ mua lại theo nhân viên — READY

Cho câu hỏi "ai mở nhiều khách mới nhưng tỷ lệ mua lại thấp; ai tái kích hoạt tốt nhất". Dùng cờ
IsNC/IsRO gốc của Bravo trên tầng nhân viên.

is_ac KHÔNG dùng ở đây: theo DNH chốt 27/08/2026, IsAC là cờ của CS (Chợ sỉ) và TK (kênh MT), không
phải chỉ số ASO của TDV — xem quy ước ở mục 1.

    WITH latest61 AS (
      SELECT EmployeeCode,MAX(SaveDate) d
      FROM dbo.FACT_TongHopKhachHang
      WHERE SaveDate>=DATEFROMPARTS(YEAR(@AsOfDate),MONTH(@AsOfDate),1) AND SaveDate<=@AsOfDate
      GROUP BY EmployeeCode
    )
    SELECT f.EmployeeCode,MAX(f.ManagerCode) ManagerCode,
           COUNT(DISTINCT f.CustomerCode) TotalCustomers,
           COUNT(DISTINCT CASE WHEN f.IsNC=1 THEN f.CustomerCode END) NewCustomers,
           COUNT(DISTINCT CASE WHEN f.IsRO=1 THEN f.CustomerCode END) RepeatCustomers,
           100.0*COUNT(DISTINCT CASE WHEN f.IsRO=1 THEN f.CustomerCode END)
             /NULLIF(COUNT(DISTINCT f.CustomerCode),0) RepeatRatePct,
           SUM(CASE WHEN f.IsNC=1 THEN f.Amount_CT ELSE 0 END) NewCustomerRevenue
    FROM dbo.FACT_TongHopKhachHang f
    JOIN latest61 l ON l.EmployeeCode=f.EmployeeCode AND l.d=f.SaveDate
    WHERE (@ManagerCode IS NULL OR f.ManagerCode=@ManagerCode)
    GROUP BY f.EmployeeCode
    ORDER BY NewCustomers DESC,RepeatRatePct;

### S62 — Khách giảm tần suất, AOV hoặc số SKU so 3 tháng trước — READY

Cho câu hỏi "khách nào giảm tần suất mua, AOV hoặc số SKU/đơn so với 3 tháng trước". So kỳ hiện tại
với kỳ 3 tháng trước đó trên CÙNG tập khách.

    WITH cur AS (
      SELECT CustomerCode,COUNT(DISTINCT OrderKey) Orders,
             SUM(Amount9) Revenue,COUNT(DISTINCT ItemCode) SKUs,
             SUM(Amount9)/NULLIF(COUNT(DISTINCT OrderKey),0) AOV
      FROM #sales WHERE DocDate>=DATEADD(month,-3,@MonthEnd) AND DocDate<@MonthEnd
      GROUP BY CustomerCode
    ), pre AS (
      SELECT CustomerCode,COUNT(DISTINCT OrderKey) Orders,
             SUM(Amount9) Revenue,COUNT(DISTINCT ItemCode) SKUs,
             SUM(Amount9)/NULLIF(COUNT(DISTINCT OrderKey),0) AOV
      FROM #sales WHERE DocDate>=DATEADD(month,-6,@MonthEnd) AND DocDate<DATEADD(month,-3,@MonthEnd)
      GROUP BY CustomerCode
    ), owner_date AS (
      SELECT CustomerCode,MAX(DocDate) d FROM #sales
      WHERE DocDate>=DATEADD(month,-3,@MonthEnd) AND DocDate<@MonthEnd
      GROUP BY CustomerCode
    ), owner AS (
      SELECT s.CustomerCode,MAX(s.EmpDMSCode) EmpDMSCode
      FROM #sales s JOIN owner_date d ON d.CustomerCode=s.CustomerCode AND d.d=s.DocDate
      GROUP BY s.CustomerCode
    )
    SELECT c.CustomerCode,n.EmployeeCode,n.Name EmployeeName,
           c.Orders,p.Orders PrevOrders,c.Orders-p.Orders OrderDelta,
           c.AOV,p.AOV PrevAOV,c.AOV-p.AOV AOVDelta,
           c.SKUs,p.SKUs PrevSKUs,c.SKUs-p.SKUs SKUDelta,
           c.Revenue,p.Revenue PrevRevenue
    FROM cur c JOIN pre p ON p.CustomerCode=c.CustomerCode
    LEFT JOIN owner o ON o.CustomerCode=c.CustomerCode
    OUTER APPLY (SELECT TOP (1) d.EmployeeCode,d.Name FROM dbo.DIM_NhanVien d
                 WHERE d.DMSId=o.EmpDMSCode ORDER BY ISNULL(d.IsDuplicate,0),d.EmployeeCode) n
    WHERE c.Orders<p.Orders OR c.AOV<p.AOV OR c.SKUs<p.SKUs
    ORDER BY (p.Revenue-c.Revenue) DESC
    OFFSET 0 ROWS FETCH NEXT 200 ROWS ONLY;

Chặn 200 dòng, xếp theo mức doanh thu mất nhiều nhất. Không chặn thì ra 7.783 dòng — đúng nhưng
không dùng làm đáp án được.

### S63 — Khách mua ít hơn khách tương đồng cùng tỉnh — READY

Cho câu hỏi "khách nào mua ít hơn các khách tương đồng cùng tỉnh/phân khúc". "Tương đồng" định nghĩa
là CÙNG TỈNH — so với trung vị tỉnh đó, không so toàn quốc.

    WITH c AS (
      SELECT CustomerCode,CityName,AreaCode,EmpDMSCode,
             SUM(Amount9) Revenue,COUNT(DISTINCT OrderKey) Orders
      FROM #sales WHERE DocDate>=DATEADD(month,-3,@MonthEnd) AND DocDate<@MonthEnd
      GROUP BY CustomerCode,CityName,AreaCode,EmpDMSCode
    ), med AS (
      SELECT DISTINCT CityName,
             PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY Revenue) OVER(PARTITION BY CityName) MedianRevenue,
             PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY Orders) OVER(PARTITION BY CityName) MedianOrders
      FROM c
    )
    SELECT c.CustomerCode,c.CityName,c.AreaCode,n.EmployeeCode,n.Name EmployeeName,
           c.Revenue,m.MedianRevenue,c.Orders,m.MedianOrders,
           100.0*c.Revenue/NULLIF(m.MedianRevenue,0) PctOfCityMedian
    FROM c JOIN med m ON m.CityName=c.CityName
    LEFT JOIN dbo.DIM_NhanVien n ON n.DMSId=c.EmpDMSCode
    WHERE c.Revenue<0.5*m.MedianRevenue
    ORDER BY (m.MedianRevenue-c.Revenue) DESC
    OFFSET 0 ROWS FETCH NEXT 200 ROWS ONLY;

Chặn 200 dòng, xếp theo khoảng cách xa trung vị tỉnh nhất (bản không chặn: 2.860 dòng).

### S64 — Cá nhân/đội dưới 80% liên tiếp và khoảng hụt — READY

Cho câu hỏi "cá nhân/đội nào dưới 80% liên tiếp 3 tháng; khoảng hụt bao nhiêu". Khác S31 (phân tầng
KPI tại từng tháng) ở chỗ đếm CHUỖI LIÊN TIẾP và cộng dồn phần hụt.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    ), e AS (
      SELECT EOMONTH(SaveDate) MonthEnd,EmployeeCode,EmployeeName,ManagerCode,AreaCode,
             MonthSaleAmount Actual,MonthSaleTarget Target,
             CASE WHEN MonthSalePercent_R<0.8 THEN 1 ELSE 0 END Below80
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
        AND (@ManagerCode IS NULL OR ManagerCode=@ManagerCode)
    ), g AS (
      SELECT *,ROW_NUMBER() OVER(PARTITION BY EmployeeCode ORDER BY MonthEnd)
               -ROW_NUMBER() OVER(PARTITION BY EmployeeCode,Below80 ORDER BY MonthEnd) Grp
      FROM e WHERE Below80=1
    )
    SELECT EmployeeCode,MAX(EmployeeName) EmployeeName,MAX(ManagerCode) ManagerCode,
           MAX(AreaCode) AreaCode,COUNT(*) MonthsBelow80,
           MIN(MonthEnd) FromMonth,MAX(MonthEnd) ToMonth,
           SUM(Target-Actual) CumulativeGap
    FROM g GROUP BY EmployeeCode,Grp
    HAVING COUNT(*)>=3
    ORDER BY CumulativeGap DESC;

### S65 — QLV có nhiều nhân viên dưới 80% nhất — READY

Cho câu hỏi "QLV nào có nhiều nhân viên dưới 80%; phần hụt của đội tập trung ở ai". Tổng hợp theo
QLV, kèm nhân viên hụt nhiều nhất trong đội.

Không cộng doanh số ở nhiều tầng (nguyên tắc pass/fail số 2): chỉ lấy tầng TDV/CTV/CS.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@MonthStart AND SaveDate<@MonthEnd
    ), e AS (
      SELECT EmployeeCode,EmployeeName,ManagerCode,AreaCode,
             MonthSaleAmount Actual,MonthSaleTarget Target,MonthSalePercent_R Pct
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
    ), agg AS (
      SELECT ManagerCode,MAX(AreaCode) AreaCode,
             COUNT(*) TeamSize,
             SUM(CASE WHEN Pct<0.8 THEN 1 ELSE 0 END) Below80Count,
             SUM(CASE WHEN Pct<0.8 THEN Target-Actual ELSE 0 END) TeamGap
      FROM e GROUP BY ManagerCode
    ), worst AS (
      SELECT ManagerCode,EmployeeCode,EmployeeName,Target-Actual EmpGap,
             ROW_NUMBER() OVER(PARTITION BY ManagerCode ORDER BY Target-Actual DESC) rn
      FROM e WHERE Pct<0.8
    )
    SELECT a.ManagerCode,a.AreaCode,a.TeamSize,a.Below80Count,
           100.0*a.Below80Count/NULLIF(a.TeamSize,0) Below80Pct,a.TeamGap,
           w.EmployeeCode WorstEmployee,w.EmployeeName WorstEmployeeName,w.EmpGap WorstGap
    FROM agg a LEFT JOIN worst w ON w.ManagerCode=a.ManagerCode AND w.rn=1
    ORDER BY a.Below80Count DESC,a.TeamGap DESC;

### S66 — Span of control và ảnh hưởng tới năng suất — PARTIAL

Cho câu hỏi "QLV nào có span of control quá lớn/nhỏ; quy mô đội có ảnh hưởng năng suất không".
Khác S32 (năng suất theo đội) ở chỗ tập trung vào QUY MÔ ĐỘI và đối chiếu với năng suất/người.

Chưa có FACT_PhatSinhNhanVien nên không tách được ảnh hưởng vào/ra/chuyển vùng — xem ghi chú S32.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    ), t AS (
      SELECT EOMONTH(SaveDate) MonthEnd,ManagerCode,MAX(AreaCode) AreaCode,
             COUNT(DISTINCT EmployeeCode) TeamSize,
             SUM(MonthSaleAmount) TeamRevenue,
             SUM(MonthSaleAmount)/NULLIF(COUNT(DISTINCT EmployeeCode),0) RevenuePerEmployee
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
      GROUP BY EOMONTH(SaveDate),ManagerCode
    ), bench AS (
      SELECT MonthEnd,AVG(TeamSize*1.0) AvgTeamSize,AVG(RevenuePerEmployee) AvgRevPerEmp
      FROM t GROUP BY MonthEnd
    )
    SELECT t.MonthEnd,t.ManagerCode,t.AreaCode,t.TeamSize,b.AvgTeamSize,
           t.TeamRevenue,t.RevenuePerEmployee,b.AvgRevPerEmp,
           CASE WHEN t.TeamSize>1.5*b.AvgTeamSize THEN 'SPAN_QUA_LON'
                WHEN t.TeamSize<0.5*b.AvgTeamSize THEN 'SPAN_QUA_NHO'
                ELSE 'BINH_THUONG' END SpanFlag,
           CASE WHEN t.RevenuePerEmployee<b.AvgRevPerEmp THEN 'NANG_SUAT_DUOI_TB'
                ELSE 'DAT' END ProductivityFlag
    FROM t JOIN bench b ON b.MonthEnd=t.MonthEnd
    ORDER BY t.MonthEnd,t.TeamSize DESC;

### S67 — Vòng đời khách theo vùng và tỷ lệ giữ chân — READY

Cho câu hỏi "số khách mới, tái kích hoạt, mua lại, ngừng mua của từng vùng; tỷ lệ giữ chân". Khác
S18 (đếm toàn công ty) ở chỗ tách theo VÙNG và tính thêm tỷ lệ giữ chân giữa hai tháng liền kề.

Chỉ đếm tầng nhân viên (TDV/CTV/CS) để không cộng trùng dòng rollup QLV.

    WITH latest67 AS (
      SELECT EmployeeCode,EOMONTH(SaveDate) MonthEnd,MAX(SaveDate) d
      FROM dbo.FACT_TongHopKhachHang
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
      GROUP BY EmployeeCode,EOMONTH(SaveDate)
    ), e AS (
      SELECT l.MonthEnd,n.AreaCode,f.CustomerCode,f.IsNC,f.IsRO
      FROM dbo.FACT_TongHopKhachHang f
      JOIN latest67 l ON l.EmployeeCode=f.EmployeeCode AND l.d=f.SaveDate
      JOIN dbo.DIM_NhanVien n ON n.EmployeeCode=f.EmployeeCode
      WHERE n.PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR n.AreaCode=@AreaCode)
    ), m AS (
      SELECT MonthEnd,AreaCode,
             COUNT(DISTINCT CustomerCode) TotalCustomers,
             COUNT(DISTINCT CASE WHEN IsNC=1 THEN CustomerCode END) NewCustomers,
             COUNT(DISTINCT CASE WHEN IsRO=1 THEN CustomerCode END) RepeatCustomers,
             COUNT(DISTINCT CASE WHEN (IsNC IS NULL OR IsNC<>1)
                                  AND (IsRO IS NULL OR IsRO<>1) THEN CustomerCode END) NoFlagCustomers
      FROM e GROUP BY MonthEnd,AreaCode
    )
    SELECT MonthEnd,AreaCode,TotalCustomers,NewCustomers,RepeatCustomers,NoFlagCustomers,
           LAG(TotalCustomers) OVER(PARTITION BY AreaCode ORDER BY MonthEnd) PrevTotal,
           100.0*RepeatCustomers/NULLIF(LAG(TotalCustomers)
             OVER(PARTITION BY AreaCode ORDER BY MonthEnd),0) RetentionPct
    FROM m ORDER BY AreaCode,MonthEnd;

### S68 — Khách mua lại/tái kích hoạt và mức phục hồi doanh thu — READY

Cho câu hỏi "khách mua lại/tái kích hoạt là ai; doanh thu phục hồi so trước khi ngừng mua". Xác định
khách có khoảng nghỉ rồi quay lại, và so doanh thu sau khi quay lại với trước khi nghỉ.

Dùng hóa đơn thật thay vì cờ IsRO, vì cần biết KHOẢNG NGHỈ bao lâu — cờ không cho biết điều đó.

    WITH o AS (
      SELECT CustomerCode,EmpDMSCode,DocDate,Amount9,
             LAG(DocDate) OVER(PARTITION BY CustomerCode ORDER BY DocDate) PrevDate
      FROM #sales
    ), gap AS (
      SELECT CustomerCode,EmpDMSCode,DocDate ReturnDate,PrevDate,
             DATEDIFF(day,PrevDate,DocDate) GapDays
      FROM o WHERE PrevDate IS NOT NULL AND DATEDIFF(day,PrevDate,DocDate)>=60
    ), sau AS (
      SELECT g.CustomerCode,g.ReturnDate,g.GapDays,SUM(s.Amount9) RevenueAfter
      FROM gap g JOIN #sales s ON s.CustomerCode=g.CustomerCode
        AND s.DocDate>=g.ReturnDate AND s.DocDate<DATEADD(month,3,g.ReturnDate)
      GROUP BY g.CustomerCode,g.ReturnDate,g.GapDays
    ), truoc AS (
      SELECT g.CustomerCode,g.ReturnDate,SUM(s.Amount9) RevenueBefore
      FROM gap g JOIN #sales s ON s.CustomerCode=g.CustomerCode
        AND s.DocDate<g.PrevDate AND s.DocDate>=DATEADD(month,-3,g.PrevDate)
      GROUP BY g.CustomerCode,g.ReturnDate
    )
    SELECT a.CustomerCode,a.ReturnDate,a.GapDays,
           ISNULL(b.RevenueBefore,0) RevenueBefore3M,a.RevenueAfter RevenueAfter3M,
           a.RevenueAfter-ISNULL(b.RevenueBefore,0) RecoveryDelta,
           100.0*a.RevenueAfter/NULLIF(b.RevenueBefore,0) RecoveryPct
    FROM sau a LEFT JOIN truoc b ON b.CustomerCode=a.CustomerCode AND b.ReturnDate=a.ReturnDate
    WHERE a.ReturnDate>=@FromDate
    ORDER BY a.RevenueAfter DESC
    OFFSET 0 ROWS FETCH NEXT 200 ROWS ONLY;

Chặn 200 dòng, xếp theo doanh thu sau khi quay lại — người đọc cần biết ca tái kích hoạt nào ĐÁNG
TIỀN nhất. Xếp theo `ReturnDate DESC` như trước chỉ cho ra ca mới nhất và ra 14.868 dòng.

### S69 — Khách im lặng 30/60/90 ngày — READY

Cho câu hỏi "khách im lặng 30/60/90 ngày là ai; lần mua gần nhất, giá trị và sản phẩm thường mua".
Khác S40 ở chỗ phân nhóm theo BA MỐC và kèm sản phẩm mua nhiều nhất của từng khách.

    WITH last AS (
      SELECT CustomerCode,MAX(DocDate) LastOrderDate,
             SUM(Amount9) Revenue12M,COUNT(DISTINCT OrderKey) Orders12M
      FROM #sales GROUP BY CustomerCode
    ), owner AS (
      SELECT s.CustomerCode,MAX(s.EmpDMSCode) EmpDMSCode
      FROM #sales s JOIN last l ON l.CustomerCode=s.CustomerCode AND l.LastOrderDate=s.DocDate
      GROUP BY s.CustomerCode
    ), topsku AS (
      SELECT CustomerCode,ItemCode,SUM(Amount9) SkuRevenue,
             ROW_NUMBER() OVER(PARTITION BY CustomerCode ORDER BY SUM(Amount9) DESC) rn
      FROM #sales GROUP BY CustomerCode,ItemCode
    )
    SELECT l.CustomerCode,n.EmployeeCode,n.Name EmployeeName,
           l.LastOrderDate,DATEDIFF(day,l.LastOrderDate,@AsOfDate) SilentDays,
           CASE WHEN DATEDIFF(day,l.LastOrderDate,@AsOfDate)>=90 THEN '90+'
                WHEN DATEDIFF(day,l.LastOrderDate,@AsOfDate)>=60 THEN '60-89'
                WHEN DATEDIFF(day,l.LastOrderDate,@AsOfDate)>=30 THEN '30-59'
                ELSE 'DANG_MUA' END SilentBand,
           l.Revenue12M,l.Orders12M,t.ItemCode TopItem,t.SkuRevenue TopItemRevenue
    FROM last l
    LEFT JOIN owner o ON o.CustomerCode=l.CustomerCode
    OUTER APPLY (SELECT TOP (1) d.EmployeeCode,d.Name FROM dbo.DIM_NhanVien d
                 WHERE d.DMSId=o.EmpDMSCode ORDER BY ISNULL(d.IsDuplicate,0),d.EmployeeCode) n
    LEFT JOIN topsku t ON t.CustomerCode=l.CustomerCode AND t.rn=1
    WHERE DATEDIFF(day,l.LastOrderDate,@AsOfDate)>=30
    ORDER BY l.Revenue12M DESC
    OFFSET 0 ROWS FETCH NEXT 200 ROWS ONLY;

Hai kết quả: bảng trên là 200 khách im lặng có doanh thu lớn nhất (ai cần gọi trước), bảng dưới là
quy mô từng mốc để biết tổng mức rủi ro. Bản cũ trả 13.887 dòng không xếp theo giá trị.

    WITH last69 AS (
      SELECT CustomerCode,MAX(DocDate) LastOrderDate,SUM(Amount9) Revenue12M
      FROM #sales GROUP BY CustomerCode
    )
    SELECT CASE WHEN DATEDIFF(day,LastOrderDate,@AsOfDate)>=90 THEN '90+'
                WHEN DATEDIFF(day,LastOrderDate,@AsOfDate)>=60 THEN '60-89'
                WHEN DATEDIFF(day,LastOrderDate,@AsOfDate)>=30 THEN '30-59'
                ELSE 'DANG_MUA' END SilentBand,
           COUNT(*) Customers,SUM(Revenue12M) RevenueAtRisk
    FROM last69 GROUP BY
           CASE WHEN DATEDIFF(day,LastOrderDate,@AsOfDate)>=90 THEN '90+'
                WHEN DATEDIFF(day,LastOrderDate,@AsOfDate)>=60 THEN '60-89'
                WHEN DATEDIFF(day,LastOrderDate,@AsOfDate)>=30 THEN '30-59'
                ELSE 'DANG_MUA' END
    ORDER BY SilentBand;

### S70 — Mức tập trung doanh thu vào top khách/sản phẩm/miền — READY

Cho câu hỏi "doanh thu phụ thuộc top 10 khách, top 10 sản phẩm và top 3 miền bao nhiêu". Khác S08
(cơ cấu kênh) ở chỗ đo MỨC TẬP TRUNG trên ba chiều cùng lúc.

    WITH tot AS (SELECT SUM(Amount9) Total FROM #sales
                 WHERE DocDate>=@MonthStart AND DocDate<@MonthEnd),
    kh AS (
      SELECT TOP 10 CustomerCode,SUM(Amount9) Rev FROM #sales
      WHERE DocDate>=@MonthStart AND DocDate<@MonthEnd
      GROUP BY CustomerCode ORDER BY SUM(Amount9) DESC
    ), sp AS (
      SELECT TOP 10 ItemCode,SUM(Amount9) Rev FROM #sales
      WHERE DocDate>=@MonthStart AND DocDate<@MonthEnd
      GROUP BY ItemCode ORDER BY SUM(Amount9) DESC
    ), mi AS (
      SELECT TOP 3 AreaCode,SUM(Amount9) Rev FROM #sales
      WHERE DocDate>=@MonthStart AND DocDate<@MonthEnd
      GROUP BY AreaCode ORDER BY SUM(Amount9) DESC
    )
    SELECT (SELECT Total FROM tot) TotalRevenue,
           (SELECT SUM(Rev) FROM kh) Top10CustomerRevenue,
           100.0*(SELECT SUM(Rev) FROM kh)/NULLIF((SELECT Total FROM tot),0) Top10CustomerPct,
           (SELECT SUM(Rev) FROM sp) Top10ItemRevenue,
           100.0*(SELECT SUM(Rev) FROM sp)/NULLIF((SELECT Total FROM tot),0) Top10ItemPct,
           (SELECT SUM(Rev) FROM mi) Top3AreaRevenue,
           100.0*(SELECT SUM(Rev) FROM mi)/NULLIF((SELECT Total FROM tot),0) Top3AreaPct;

### S71 — Top khách tăng/giảm mạnh nhất và ảnh hưởng tới tổng — READY

Cho câu hỏi "top khách tăng/giảm mạnh nhất từng tháng; ảnh hưởng bao nhiêu tới tổng". Khác S20
(luồng khách) ở chỗ đo ĐÓNG GÓP TUYỆT ĐỐI vào biến động tổng.

    WITH m AS (
      SELECT EOMONTH(DocDate) MonthEnd,CustomerCode,SUM(Amount9) Revenue
      FROM #sales GROUP BY EOMONTH(DocDate),CustomerCode
    ), d AS (
      SELECT MonthEnd,CustomerCode,Revenue,
             Revenue-LAG(Revenue) OVER(PARTITION BY CustomerCode ORDER BY MonthEnd) Delta
      FROM m
    ), tot AS (
      SELECT MonthEnd,SUM(Revenue) TotalRevenue,
             SUM(Revenue)-LAG(SUM(Revenue)) OVER(ORDER BY MonthEnd) TotalDelta
      FROM m GROUP BY MonthEnd
    )
    , x AS (
      SELECT d.MonthEnd,d.CustomerCode,d.Revenue,d.Delta,t.TotalDelta,
             100.0*d.Delta/NULLIF(ABS(t.TotalDelta),0) ContributionPctOfChange,
             CASE WHEN d.Delta>0 THEN 'TANG' ELSE 'GIAM' END Direction
      FROM d JOIN tot t ON t.MonthEnd=d.MonthEnd
      WHERE d.Delta IS NOT NULL
    )
    SELECT * FROM (
      SELECT *,ROW_NUMBER() OVER(PARTITION BY MonthEnd,Direction
                                 ORDER BY ABS(Delta) DESC) rn
      FROM x
    ) r
    WHERE r.rn<=10
    ORDER BY r.MonthEnd DESC,r.Direction,r.rn;

Câu hỏi hỏi **top** khách tăng/giảm mỗi tháng nên chỉ giữ 10 khách tăng mạnh nhất và 10 khách giảm
mạnh nhất của TỪNG tháng. Bản cũ trả mọi khách × mọi tháng: 69.284 dòng.

### S72 — Phân rã nguyên nhân giảm doanh thu theo SKU — READY

Cho câu hỏi "SKU nào giảm do ít khách, ít đơn, giảm lượng/đơn hay giảm giá bán". Tách BỐN nguyên
nhân thành bốn cột riêng thay vì để người đọc suy luận.

Sản lượng chỉ tính UnitPrice > 0 (nguyên tắc pass/fail số 5) — hàng tặng không vào paid quantity.

    WITH cur AS (
      SELECT ItemCode,COUNT(DISTINCT CustomerCode) Customers,COUNT(DISTINCT OrderKey) Orders,
             SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END) PaidQty,
             SUM(Amount9) Revenue,
             SUM(Amount9)/NULLIF(SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END),0) AvgPrice
      FROM #sales WHERE DocDate>=@MonthStart AND DocDate<@MonthEnd
      GROUP BY ItemCode
    ), pre AS (
      SELECT ItemCode,COUNT(DISTINCT CustomerCode) Customers,COUNT(DISTINCT OrderKey) Orders,
             SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END) PaidQty,
             SUM(Amount9) Revenue,
             SUM(Amount9)/NULLIF(SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END),0) AvgPrice
      FROM #sales WHERE DocDate>=DATEADD(month,-1,@MonthStart) AND DocDate<@MonthStart
      GROUP BY ItemCode
    )
    SELECT c.ItemCode,c.Revenue,p.Revenue PrevRevenue,c.Revenue-p.Revenue RevenueDelta,
           c.Customers-p.Customers CustomerDelta,
           c.Orders-p.Orders OrderDelta,
           c.PaidQty-p.PaidQty QuantityDelta,
           c.AvgPrice-p.AvgPrice PriceDelta,
           CASE WHEN c.Customers<p.Customers THEN 'IT_KHACH'
                WHEN c.Orders<p.Orders THEN 'IT_DON'
                WHEN c.PaidQty<p.PaidQty THEN 'GIAM_LUONG'
                WHEN c.AvgPrice<p.AvgPrice THEN 'GIAM_GIA'
                ELSE 'KHAC' END NguyenNhanChinh
    FROM cur c JOIN pre p ON p.ItemCode=c.ItemCode
    WHERE c.Revenue<p.Revenue
    ORDER BY (p.Revenue-c.Revenue) DESC;

### S73 — SKU tăng độ phủ nhưng giảm doanh thu/khách — DERIVED

Cho câu hỏi "SKU nào độ phủ khách tăng nhưng doanh thu/khách giảm". Định nghĩa "độ phủ" là số khách
mua SKU đó — cần DNH chốt nếu muốn định nghĩa khác (vd tỷ lệ trên tổng khách hoạt động).

    WITH cur AS (
      SELECT ItemCode,COUNT(DISTINCT CustomerCode) Customers,SUM(Amount9) Revenue,
             SUM(Amount9)/NULLIF(COUNT(DISTINCT CustomerCode),0) RevenuePerCustomer
      FROM #sales WHERE DocDate>=DATEADD(month,-3,@MonthEnd) AND DocDate<@MonthEnd
      GROUP BY ItemCode
    ), pre AS (
      SELECT ItemCode,COUNT(DISTINCT CustomerCode) Customers,SUM(Amount9) Revenue,
             SUM(Amount9)/NULLIF(COUNT(DISTINCT CustomerCode),0) RevenuePerCustomer
      FROM #sales WHERE DocDate>=DATEADD(month,-6,@MonthEnd) AND DocDate<DATEADD(month,-3,@MonthEnd)
      GROUP BY ItemCode
    )
    SELECT c.ItemCode,c.Customers,p.Customers PrevCustomers,c.Customers-p.Customers CoverageDelta,
           c.RevenuePerCustomer,p.RevenuePerCustomer PrevRevenuePerCustomer,
           c.RevenuePerCustomer-p.RevenuePerCustomer RevPerCusDelta,
           c.Revenue,p.Revenue PrevRevenue
    FROM cur c JOIN pre p ON p.ItemCode=c.ItemCode
    WHERE c.Customers>p.Customers AND c.RevenuePerCustomer<p.RevenuePerCustomer
    ORDER BY (p.RevenuePerCustomer-c.RevenuePerCustomer) DESC;

### S74 — Cặp sản phẩm mua cùng và khách phù hợp bán combo — DERIVED

Cho câu hỏi "cặp sản phẩm nào thường mua cùng; khách nào phù hợp bán combo nhưng chưa mua". Ngưỡng
"thường mua cùng" đề xuất là >=5 khách chung — cần DNH chốt.

Trả về hai kết quả tách rời, KHÔNG ghép cặp với khách trong cùng một bảng. Bản chạy ngày 28/08/2026
ghép chung và ra 1.167.582 dòng: mỗi cặp bị nhân bản một lần cho từng khách ứng viên, dòng thống kê
cặp lặp lại y hệt nên không đọc được. Cặp là một tầng, khách là tầng khác — trộn hai tầng vào một
bảng là đúng lỗi "trả nguyên liệu thô" mà mục 5 cấm.

Kết quả 1 — cặp sản phẩm thường mua cùng:

    WITH ck AS (
      SELECT DISTINCT CustomerCode,ItemCode FROM #sales
      WHERE DocDate>=DATEADD(month,-3,@MonthEnd) AND DocDate<@MonthEnd
    ), pair AS (
      SELECT a.ItemCode ItemA,b.ItemCode ItemB,COUNT(DISTINCT a.CustomerCode) SharedCustomers
      FROM ck a JOIN ck b ON b.CustomerCode=a.CustomerCode AND b.ItemCode>a.ItemCode
      GROUP BY a.ItemCode,b.ItemCode
      HAVING COUNT(DISTINCT a.CustomerCode)>=5
    ), cnt AS (SELECT ItemCode,COUNT(DISTINCT CustomerCode) Buyers FROM ck GROUP BY ItemCode)
    SELECT TOP (50) p.ItemA,p.ItemB,p.SharedCustomers,
           ca.Buyers BuyersA,cb.Buyers BuyersB,
           100.0*p.SharedCustomers/NULLIF(ca.Buyers,0) AttachRatePct,
           ca.Buyers-p.SharedCustomers CandidatesBuyAOnly
    FROM pair p
    JOIN cnt ca ON ca.ItemCode=p.ItemA
    JOIN cnt cb ON cb.ItemCode=p.ItemB
    ORDER BY p.SharedCustomers DESC;

Kết quả 2 — khách mua A nhưng chưa mua B, chỉ trong 20 cặp mạnh nhất, xếp theo doanh thu khách:

    WITH ck AS (
      SELECT DISTINCT CustomerCode,ItemCode FROM #sales
      WHERE DocDate>=DATEADD(month,-3,@MonthEnd) AND DocDate<@MonthEnd
    ), pair AS (
      SELECT TOP (20) a.ItemCode ItemA,b.ItemCode ItemB,
             COUNT(DISTINCT a.CustomerCode) SharedCustomers
      FROM ck a JOIN ck b ON b.CustomerCode=a.CustomerCode AND b.ItemCode>a.ItemCode
      GROUP BY a.ItemCode,b.ItemCode
      HAVING COUNT(DISTINCT a.CustomerCode)>=5
      ORDER BY COUNT(DISTINCT a.CustomerCode) DESC
    ), rev AS (
      SELECT CustomerCode,SUM(Amount9) Revenue3M FROM #sales
      WHERE DocDate>=DATEADD(month,-3,@MonthEnd) AND DocDate<@MonthEnd
      GROUP BY CustomerCode
    ), owner_date AS (
      SELECT CustomerCode,MAX(DocDate) d FROM #sales
      WHERE DocDate>=DATEADD(month,-3,@MonthEnd) AND DocDate<@MonthEnd
      GROUP BY CustomerCode
    ), owner AS (
      SELECT s.CustomerCode,MAX(s.EmpDMSCode) EmpDMSCode
      FROM #sales s JOIN owner_date d ON d.CustomerCode=s.CustomerCode AND d.d=s.DocDate
      GROUP BY s.CustomerCode
    )
    SELECT TOP (500) p.ItemA,p.ItemB,p.SharedCustomers,
           x.CustomerCode,n.EmployeeCode,n.Name EmployeeName,r.Revenue3M
    FROM pair p
    JOIN ck x ON x.ItemCode=p.ItemA
      AND NOT EXISTS(SELECT 1 FROM ck y WHERE y.CustomerCode=x.CustomerCode AND y.ItemCode=p.ItemB)
    LEFT JOIN rev r ON r.CustomerCode=x.CustomerCode
    LEFT JOIN owner o ON o.CustomerCode=x.CustomerCode
    OUTER APPLY (SELECT TOP (1) d.EmployeeCode,d.Name FROM dbo.DIM_NhanVien d
                 WHERE d.DMSId=o.EmpDMSCode ORDER BY ISNULL(d.IsDuplicate,0),d.EmployeeCode) n
    ORDER BY r.Revenue3M DESC,p.SharedCustomers DESC;

### S75 — Khách chưa gán TDV, sai mã hoặc thiếu mapping — READY

Cho câu hỏi "khách nào chưa gán TDV, sai mã, sai tỉnh/vùng hoặc không có tên trong DMS". Khác S38
(chất lượng mapping tổng quát) ở chỗ liệt kê TỪNG KHÁCH có vấn đề để xử lý được ngay.

    SELECT s.CustomerCode,
           MAX(s.AreaCode) AreaCode,MAX(s.CityName) CityName,
           MAX(s.EmpDMSCode) EmpDMSCode,MAX(n.EmployeeCode) EmployeeCode,
           SUM(s.Amount9) Revenue,COUNT(DISTINCT s.OrderKey) Orders,
           CASE WHEN MAX(s.EmpDMSCode) IS NULL OR MAX(s.EmpDMSCode)='' THEN 1 ELSE 0 END ThieuMaNV,
           CASE WHEN MAX(n.EmployeeCode) IS NULL THEN 1 ELSE 0 END KhongKhopDanhMucNV,
           CASE WHEN MAX(s.AreaCode)='CHUA_XAC_DINH' THEN 1 ELSE 0 END ThieuMappingVung,
           CASE WHEN MAX(k.Name) IS NULL THEN 1 ELSE 0 END KhongCoTenTrongDMS
    FROM #sales s
    LEFT JOIN dbo.DIM_NhanVien n ON n.DMSId=s.EmpDMSCode
    LEFT JOIN (SELECT Code,Name FROM dbo.DMS_KhachHang
               UNION ALL SELECT Code,Name FROM dbo.DMSSX_KhachHang) k ON k.Code=s.CustomerCode
    WHERE s.DocDate>=@MonthStart AND s.DocDate<@MonthEnd
    GROUP BY s.CustomerCode
    HAVING MAX(s.EmpDMSCode) IS NULL OR MAX(s.EmpDMSCode)=''
        OR MAX(n.EmployeeCode) IS NULL
        OR MAX(s.AreaCode)='CHUA_XAC_DINH'
        OR MAX(k.Name) IS NULL
    ORDER BY Revenue DESC;

### S76 — Checklist tồn đọng cuối tháng — READY

Cho câu hỏi "cuối tháng còn tồn đọng gì: target thiếu, khách chưa gán, đơn chưa xử lý". Gộp các
kiểm tra rời thành MỘT bảng đếm để dùng làm checklist.

Mỗi dòng là một loại tồn đọng kèm số lượng; không trộn các loại vào một con số tổng.

    WITH thieu_target AS (
      SELECT COUNT(*) n FROM (
        SELECT EmployeeCode FROM dbo.FACT_ThongKeTinhLuong
        WHERE SaveDate>=@MonthStart AND SaveDate<@MonthEnd
          AND PositionCode IN ('TDV','CTV','CS')
          AND (MonthSaleTarget IS NULL OR MonthSaleTarget<=0)
        GROUP BY EmployeeCode) x
    ), khach_chua_gan AS (
      SELECT COUNT(DISTINCT CustomerCode) n FROM #sales
      WHERE DocDate>=@MonthStart AND DocDate<@MonthEnd
        AND (EmpDMSCode IS NULL OR EmpDMSCode='')
    ), thieu_vung AS (
      SELECT COUNT(DISTINCT CustomerCode) n FROM #sales
      WHERE DocDate>=@MonthStart AND DocDate<@MonthEnd AND AreaCode='CHUA_XAC_DINH'
    ), don_tuong_lai AS (
      SELECT COUNT(DISTINCT OrderKey) n FROM #sales WHERE DocDate>CAST(GETDATE() AS date)
    )
    SELECT 'Nhan vien thieu target' LoaiTonDong,(SELECT n FROM thieu_target) SoLuong
    UNION ALL SELECT 'Khach chua gan nhan vien',(SELECT n FROM khach_chua_gan)
    UNION ALL SELECT 'Khach thieu mapping vung',(SELECT n FROM thieu_vung)
    UNION ALL SELECT 'Don ghi ngay tuong lai',(SELECT n FROM don_tuong_lai);

### S77 — Tỷ lệ hàng trả/điều chỉnh trên doanh thu theo tháng và kênh — READY

Cho câu hỏi "tỷ lệ hàng trả/điều chỉnh trên doanh thu theo tháng và kênh; nơi nào vượt ngưỡng". Khác
S09 (liệt kê giao dịch bất thường) ở chỗ trả về THẲNG TỶ LỆ và cờ vượt ngưỡng.

Ngưỡng 2% là đề xuất để có kết quả chạy được — cần DNH chốt trước khi coi cờ này là kết luận.

    WITH m AS (
      SELECT EOMONTH(DocDate) MonthEnd,Channel,AreaCode,
             SUM(CASE WHEN Amount9>0 THEN Amount9 ELSE 0 END) GrossRevenue,
             SUM(CASE WHEN Amount9<0 OR DocCode='HC' THEN ABS(Amount9) ELSE 0 END) ReturnAdjustment,
             COUNT(DISTINCT CASE WHEN Amount9<0 OR DocCode='HC' THEN OrderKey END) ReturnOrders,
             COUNT(DISTINCT OrderKey) TotalOrders
      FROM #sales GROUP BY EOMONTH(DocDate),Channel,AreaCode
    )
    SELECT MonthEnd,Channel,AreaCode,GrossRevenue,ReturnAdjustment,ReturnOrders,TotalOrders,
           100.0*ReturnAdjustment/NULLIF(GrossRevenue,0) ReturnRatePct,
           CASE WHEN 100.0*ReturnAdjustment/NULLIF(GrossRevenue,0)>2 THEN 'VUOT_NGUONG'
                ELSE 'TRONG_NGUONG' END ThresholdFlag
    FROM m ORDER BY ReturnRatePct DESC;

### S78 — Trả hàng, hàng tặng trên doanh thu theo vùng — PARTIAL

Cho câu hỏi "tỷ lệ trả hàng, chiết khấu và hàng tặng trên doanh thu của từng vùng thay đổi ra sao".

Hàng tặng nhận diện bằng `UnitPrice = 0 AND Quantity > 0` (nhất quán với nguyên tắc pass/fail số 5).
**Phần chiết khấu là PARTIAL**: chưa xác nhận cột chiết khấu nào tồn tại trên `vHoaDonTotal`/
`vHoaDonETCTotal`. Không suy ra chiết khấu bằng cách lấy hiệu giá niêm yết trừ giá bán — sai lệch do
đổi bảng giá sẽ bị hiểu nhầm thành chiết khấu. Chạy lệnh kiểm cột ở mục 2 rồi mới bổ sung.

    WITH m AS (
      SELECT EOMONTH(DocDate) MonthEnd,AreaCode,
             SUM(CASE WHEN Amount9>0 THEN Amount9 ELSE 0 END) GrossRevenue,
             SUM(CASE WHEN Amount9<0 OR DocCode='HC' THEN ABS(Amount9) ELSE 0 END) ReturnAmount,
             SUM(CASE WHEN UnitPrice=0 AND Quantity>0 THEN Quantity ELSE 0 END) GiftQuantity,
             COUNT(DISTINCT CASE WHEN UnitPrice=0 AND Quantity>0 THEN OrderKey END) GiftOrders
      FROM #sales GROUP BY EOMONTH(DocDate),AreaCode
    )
    SELECT MonthEnd,AreaCode,GrossRevenue,ReturnAmount,GiftQuantity,GiftOrders,
           100.0*ReturnAmount/NULLIF(GrossRevenue,0) ReturnRatePct,
           100.0*GiftOrders/NULLIF(COUNT(1) OVER(PARTITION BY MonthEnd,AreaCode),0) GiftOrderSharePct,
           ReturnAmount-LAG(ReturnAmount) OVER(PARTITION BY AreaCode ORDER BY MonthEnd) ReturnDelta
    FROM m ORDER BY AreaCode,MonthEnd;

### S79 — Lũy kế YTD so kế hoạch, cùng kỳ và mức bình quân còn phải đạt — PARTIAL

Cho câu hỏi "lũy kế YTD so kế hoạch và cùng kỳ năm trước; cần bình quân bao nhiêu mỗi tháng còn lại
để đạt kế hoạch năm". Khác S02 (từng tháng) ở chỗ trả về LŨY KẾ và mức bình quân còn phải đạt.

**PARTIAL**: kế hoạch năm được cộng dồn từ `MonthSaleTarget` của các tháng đã có snapshot. Nếu DNH
có bảng kế hoạch năm riêng thì phải dùng bảng đó — số cộng dồn này chỉ là xấp xỉ khi các tháng cuối
năm chưa có snapshot.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=DATEFROMPARTS(YEAR(@AsOfDate)-1,1,1) AND SaveDate<=@AsOfDate
    ), k AS (
      SELECT YEAR(SaveDate) Yr,MONTH(SaveDate) Mth,
             SUM(MonthSaleAmount) Actual,SUM(MonthSaleTarget) Target
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
      GROUP BY YEAR(SaveDate),MONTH(SaveDate)
    ), ytd AS (
      SELECT Yr,SUM(Actual) YtdActual,SUM(Target) YtdTarget,MAX(Mth) LastMonth
      FROM k WHERE Mth<=MONTH(@AsOfDate) GROUP BY Yr
    )
    SELECT c.Yr,c.YtdActual,c.YtdTarget,
           c.YtdActual-c.YtdTarget YtdGap,
           100.0*c.YtdActual/NULLIF(c.YtdTarget,0) YtdAchievementPct,
           p.YtdActual PriorYearYtdActual,
           100.0*(c.YtdActual-p.YtdActual)/NULLIF(p.YtdActual,0) YoYGrowthPct,
           12-MONTH(@AsOfDate) MonthsRemaining,
           CAST(NULL AS decimal(18,2)) AnnualTarget,
           CAST(NULL AS decimal(18,2)) RequiredMonthlyAverage,
           'THIEU_KE_HOACH_NAM' RequiredAverageStatus
    FROM ytd c LEFT JOIN ytd p ON p.Yr=c.Yr-1
    WHERE c.Yr=YEAR(@AsOfDate);

### S80 — Mùa vụ theo kênh và mức lệch của tháng hiện tại — PARTIAL

Cho câu hỏi "tháng nào mùa vụ cao/thấp nhất theo kênh và nhóm sản phẩm; tháng hiện tại lệch mô hình
bao nhiêu". Khác S06 (đường trung bình trượt toàn công ty) ở chỗ tách theo KÊNH và trả về chỉ số mùa
vụ cùng mức lệch.

**PARTIAL phần nhóm sản phẩm**: chưa xác nhận cột `GroupCode` có trên view hóa đơn — xem lệnh kiểm
cột ở mục 2. Trước khi xác nhận thì chỉ chạy được theo kênh.

    WITH m AS (
      SELECT YEAR(DocDate) Yr,MONTH(DocDate) Mth,Channel,SUM(Amount9) Revenue
      FROM #sales GROUP BY YEAR(DocDate),MONTH(DocDate),Channel
    ), idx AS (
      SELECT Mth,Channel,AVG(Revenue) AvgMonthRevenue FROM m GROUP BY Mth,Channel
    ), base AS (
      SELECT Channel,AVG(AvgMonthRevenue) OverallAvg FROM idx GROUP BY Channel
    )
    SELECT i.Channel,i.Mth,i.AvgMonthRevenue,b.OverallAvg,
           100.0*i.AvgMonthRevenue/NULLIF(b.OverallAvg,0) SeasonalIndexPct,
           cur.Revenue CurrentMonthRevenue,
           cur.Revenue-i.AvgMonthRevenue DeviationFromSeasonal,
           100.0*(cur.Revenue-i.AvgMonthRevenue)/NULLIF(i.AvgMonthRevenue,0) DeviationPct
    FROM idx i
    JOIN base b ON b.Channel=i.Channel
    LEFT JOIN m cur ON cur.Channel=i.Channel AND cur.Mth=i.Mth
      AND cur.Yr=YEAR(@AsOfDate) AND cur.Mth=MONTH(@AsOfDate)
    ORDER BY i.Channel,SeasonalIndexPct DESC;

### S81 — Doanh thu gắn với khách chưa gán người phụ trách — PARTIAL

Cho câu hỏi "địa bàn trống, nhân viên nghỉ/chuyển vùng hoặc khách chưa gán người phụ trách ảnh hưởng
bao nhiêu doanh thu". Khác S17 (đếm khách bị đổi mã) ở chỗ QUY RA TIỀN.

**PARTIAL**: không có bảng lịch sử phân công nên không tách được "nhân viên nghỉ" khỏi "khách chưa
gán". Ba nhóm đo được là: khách không có mã nhân viên, mã nhân viên không khớp danh mục, và khách bị
đổi người phụ trách giữa các tháng. Không suy đoán lý do nghỉ việc từ dữ liệu hóa đơn.

    WITH t AS (
      SELECT s.CustomerCode,EOMONTH(s.DocDate) MonthEnd,
             MAX(s.AreaCode) AreaCode,SUM(s.Amount9) Revenue,
             COUNT(DISTINCT s.EmpDMSCode) EmployeeCodeCount,
             MAX(CASE WHEN s.EmpDMSCode IS NULL OR s.EmpDMSCode='' THEN 1 ELSE 0 END) ThieuMaNV,
             MAX(CASE WHEN n.EmployeeCode IS NULL THEN 1 ELSE 0 END) KhongKhopDanhMuc
      FROM #sales s LEFT JOIN dbo.DIM_NhanVien n ON n.DMSId=s.EmpDMSCode
      GROUP BY s.CustomerCode,EOMONTH(s.DocDate)
    )
    SELECT MonthEnd,AreaCode,
           SUM(CASE WHEN ThieuMaNV=1 THEN Revenue ELSE 0 END) RevenueThieuMaNV,
           SUM(CASE WHEN KhongKhopDanhMuc=1 THEN Revenue ELSE 0 END) RevenueKhongKhopDanhMuc,
           SUM(CASE WHEN EmployeeCodeCount>1 THEN Revenue ELSE 0 END) RevenueDoiNguoiPhuTrach,
           SUM(Revenue) TotalRevenue,
           100.0*SUM(CASE WHEN ThieuMaNV=1 OR KhongKhopDanhMuc=1 OR EmployeeCodeCount>1
                          THEN Revenue ELSE 0 END)/NULLIF(SUM(Revenue),0) RevenueAtRiskPct
    FROM t GROUP BY MonthEnd,AreaCode ORDER BY MonthEnd,RevenueAtRiskPct DESC;

### S82 — Định lượng các nhóm rủi ro không đạt kế hoạch — DERIVED

Cho câu hỏi "ba rủi ro lớn nhất khiến không đạt kế hoạch là gì; mỗi rủi ro ảnh hưởng ước tính bao
nhiêu tiền". SQL trả về CÁC NHÓM RỦI RO ĐO ĐƯỢC kèm số tiền, xếp theo mức ảnh hưởng — việc chọn ra
ba rủi ro hàng đầu là đọc ba dòng đầu, không cần suy luận thêm.

**DERIVED**: bốn nhóm dưới đây là các rủi ro đo được từ dữ liệu có sẵn, không phải danh mục rủi ro
chính thức của DNH. Nếu DNH có khung rủi ro riêng thì phải map lại.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@MonthStart AND SaveDate<=@AsOfDate
    ), e AS (
      SELECT EmployeeCode,ManagerCode,MonthSaleAmount Actual,MonthSaleTarget Target
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
    ), r1 AS (
      SELECT SUM(Target-Actual) v FROM e WHERE Actual<0.8*Target
    ), r2 AS (
      SELECT SUM(Prior3M/3.0-Cur) v FROM (
        SELECT CustomerCode,
          SUM(CASE WHEN DocDate>=@MonthStart AND DocDate<=@AsOfDate THEN Amount9 ELSE 0 END) Cur,
          SUM(CASE WHEN DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthStart
                   THEN Amount9 ELSE 0 END) Prior3M
        FROM #sales GROUP BY CustomerCode) x
      WHERE Cur=0 AND Prior3M>0
    ), r3 AS (
      SELECT SUM(ABS(Amount9)) v FROM #sales
      WHERE DocDate>=@MonthStart AND DocDate<=@AsOfDate AND (Amount9<0 OR DocCode='HC')
    ), r4 AS (
      SELECT SUM(Amount9) v FROM #sales s
      LEFT JOIN dbo.DIM_NhanVien n ON n.DMSId=s.EmpDMSCode
      WHERE s.DocDate>=@MonthStart AND s.DocDate<=@AsOfDate
        AND (s.EmpDMSCode IS NULL OR s.EmpDMSCode='' OR n.EmployeeCode IS NULL)
    )
    SELECT 'Nhan vien duoi 80% ke hoach' RiskGroup,(SELECT v FROM r1) EstimatedImpact
    UNION ALL SELECT 'Khach ngung mua so binh quan 3 thang',(SELECT v FROM r2)
    UNION ALL SELECT 'Hang tra va dieu chinh',(SELECT v FROM r3)
    UNION ALL SELECT 'Doanh thu chua gan nguoi phu trach',(SELECT v FROM r4)
    ORDER BY EstimatedImpact DESC;

### S83 — Khách ưu tiên tuần này theo bốn mục tiêu — PARTIAL

Cho câu hỏi "danh sách khách ưu tiên tuần này theo bốn mục tiêu: giữ khách lớn, tái kích hoạt, thu
nợ và bán chéo". Khác S48 (một nhãn hành động chung) ở chỗ tách RIÊNG bốn mục tiêu, mỗi khách có thể
xuất hiện ở nhiều mục tiêu.

Chỉ trả về khách trúng ít nhất MỘT mục tiêu, xếp theo số mục tiêu trúng. Bản chạy 28/08/2026 không
lọc nên ra 13.457 dòng gồm cả khách không trúng mục tiêu nào — đó là danh sách khách hoạt động, không
phải danh sách ưu tiên.

**PARTIAL — mục tiêu thu nợ**: công nợ KHÔNG lấy từ hóa đơn. Phải gọi `usp_DeptAccDueDate_GetData`
như `backend/report_templates.py` đang làm — công thức tự tính từ `BRV_HTTDuDK` đã từng thổi nợ lên
4–15 lần. Cột `OverdueAmount` dưới đây là chỗ ghép kết quả SP đó vào, không phải số tự tính.

    WITH c AS (
      SELECT CustomerCode,MAX(DocDate) LastPurchaseDate,
        COUNT(DISTINCT ItemCode) SkuCount,
        SUM(CASE WHEN DocDate>=@MonthStart AND DocDate<@MonthEnd THEN Amount9 ELSE 0 END) Cur,
        SUM(CASE WHEN DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthStart
                 THEN Amount9 ELSE 0 END) Prior3M
      FROM #sales GROUP BY CustomerCode
    ), owner AS (
      SELECT s.CustomerCode,MAX(s.EmpDMSCode) EmpDMSCode
      FROM #sales s JOIN c ON c.CustomerCode=s.CustomerCode AND c.LastPurchaseDate=s.DocDate
      GROUP BY s.CustomerCode
    ), avgsku AS (SELECT AVG(SkuCount*1.0) AvgSku FROM c WHERE Cur>0),
    g AS (
      SELECT c.CustomerCode,o.EmpDMSCode,
             c.LastPurchaseDate,DATEDIFF(day,c.LastPurchaseDate,@AsOfDate) SilentDays,
             c.Cur,c.Prior3M,c.SkuCount,a.AvgSku,
             CASE WHEN c.Cur>0 AND c.Cur<c.Prior3M/3.0
                    AND c.Prior3M>=(SELECT AVG(Prior3M) FROM c) THEN 1 ELSE 0 END MucTieu_GiuKhachLon,
             CASE WHEN c.Cur=0 AND c.Prior3M>0 THEN 1 ELSE 0 END MucTieu_TaiKichHoat,
             CASE WHEN c.Cur>0 AND c.SkuCount<a.AvgSku THEN 1 ELSE 0 END MucTieu_BanCheo
      FROM c LEFT JOIN owner o ON o.CustomerCode=c.CustomerCode CROSS JOIN avgsku a
    )
    SELECT TOP (200) g.CustomerCode,
           g.MucTieu_GiuKhachLon+g.MucTieu_TaiKichHoat+g.MucTieu_BanCheo SoMucTieuTrung,
           g.MucTieu_GiuKhachLon,g.MucTieu_TaiKichHoat,g.MucTieu_BanCheo,
           CAST(NULL AS decimal(18,2)) OverdueAmount,
           n.EmployeeCode,n.Name EmployeeName,
           g.LastPurchaseDate,g.SilentDays,g.Cur,g.Prior3M,g.SkuCount,g.AvgSku
    FROM g OUTER APPLY (SELECT TOP (1) d.EmployeeCode,d.Name FROM dbo.DIM_NhanVien d
                        WHERE d.DMSId=g.EmpDMSCode ORDER BY ISNULL(d.IsDuplicate,0),d.EmployeeCode) n
    WHERE g.MucTieu_GiuKhachLon=1 OR g.MucTieu_TaiKichHoat=1 OR g.MucTieu_BanCheo=1
    ORDER BY SoMucTieuTrung DESC,g.Prior3M DESC;

### S84 — Ưu tiên đóng gap: khách, sản phẩm và nhân viên — READY

Cho câu hỏi "hôm nay/tuần này cần ưu tiên khách hàng, sản phẩm và nhân viên nào để đóng gap lớn
nhất". Trả về ba danh sách trong một kết quả, mỗi dòng ghi rõ thuộc chiều nào và mức hụt bao nhiêu.

Xếp theo mức hụt tuyệt đối so bình quân ba tháng trước, vì đó là phần có cơ sở đóng lại được.

    WITH kh AS (
      SELECT TOP (20) 'KHACH_HANG' Chieu,CustomerCode MaDoiTuong,
        SUM(CASE WHEN DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthStart
                 THEN Amount9 ELSE 0 END)/3.0
        -SUM(CASE WHEN DocDate>=@MonthStart AND DocDate<=@AsOfDate THEN Amount9 ELSE 0 END) MucHut
      FROM #sales GROUP BY CustomerCode ORDER BY MucHut DESC
    ), sp AS (
      SELECT TOP (20) 'SAN_PHAM' Chieu,ItemCode MaDoiTuong,
        SUM(CASE WHEN DocDate>=DATEADD(month,-3,@MonthStart) AND DocDate<@MonthStart
                 THEN Amount9 ELSE 0 END)/3.0
        -SUM(CASE WHEN DocDate>=@MonthStart AND DocDate<=@AsOfDate THEN Amount9 ELSE 0 END) MucHut
      FROM #sales GROUP BY ItemCode ORDER BY MucHut DESC
    ), nv AS (
      SELECT TOP (20) 'NHAN_VIEN' Chieu,EmployeeCode MaDoiTuong,
             MAX(MonthSaleTarget)-MAX(MonthSaleAmount) MucHut
      FROM (SELECT *,DENSE_RANK() OVER(
              PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
            FROM dbo.FACT_ThongKeTinhLuong
            WHERE SaveDate>=@MonthStart AND SaveDate<=@AsOfDate) b
      WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@ManagerCode IS NULL OR ManagerCode=@ManagerCode)
      GROUP BY EmployeeCode ORDER BY MucHut DESC
    )
    SELECT * FROM kh
    UNION ALL SELECT * FROM sp
    UNION ALL SELECT * FROM nv
    ORDER BY Chieu,MucHut DESC;

### S85 — Ramp-up của nhân viên mới so chuẩn cùng vai trò — DERIVED

Cho câu hỏi "nhân viên mới đạt ramp-up thế nào sau 1/2/3/6 tháng so với chuẩn cùng vai trò". Khác
S32 (năng suất theo đội) ở chỗ đo theo SỐ THÁNG THÂM NIÊN, không theo tháng dương lịch.

**DERIVED**: mốc bắt đầu lấy là tháng đầu tiên nhân viên xuất hiện trong `FACT_ThongKeTinhLuong`
trong cửa sổ truy vấn. Đây là XẤP XỈ ngày vào làm — người vào trước `@FromDate` sẽ bị tính nhầm là
mới. Lọc `FirstMonth > @FromDate` để loại bớt, nhưng chỉ dùng được kết luận chắc chắn khi DNH cấp
ngày vào làm chính thức.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    ), e AS (
      SELECT EOMONTH(SaveDate) MonthEnd,EmployeeCode,EmployeeName,PositionCode,ManagerCode,
             MonthSaleAmount Actual,MonthSaleTarget Target
      FROM b WHERE SnapshotRank=1 AND PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
    ), first_m AS (
      SELECT EmployeeCode,MIN(MonthEnd) FirstMonth FROM e GROUP BY EmployeeCode
    ), ten AS (
      SELECT e.*,f.FirstMonth,
             DATEDIFF(month,f.FirstMonth,e.MonthEnd)+1 TenureMonth
      FROM e JOIN first_m f ON f.EmployeeCode=e.EmployeeCode
    ), bench AS (
      SELECT PositionCode,AVG(Actual) BenchmarkRevenue
      FROM ten WHERE TenureMonth>=12 GROUP BY PositionCode
    )
    SELECT t.EmployeeCode,MAX(t.EmployeeName) EmployeeName,MAX(t.PositionCode) PositionCode,
           MAX(t.ManagerCode) ManagerCode,MAX(t.FirstMonth) FirstMonth,
           MAX(CASE WHEN t.TenureMonth=1 THEN t.Actual END) Month1,
           MAX(CASE WHEN t.TenureMonth=2 THEN t.Actual END) Month2,
           MAX(CASE WHEN t.TenureMonth=3 THEN t.Actual END) Month3,
           MAX(CASE WHEN t.TenureMonth=6 THEN t.Actual END) Month6,
           MAX(bh.BenchmarkRevenue) BenchmarkRevenue,
           100.0*MAX(CASE WHEN t.TenureMonth=3 THEN t.Actual END)
             /NULLIF(MAX(bh.BenchmarkRevenue),0) RampPctAt3M
    FROM ten t LEFT JOIN bench bh ON bh.PositionCode=t.PositionCode
    WHERE t.FirstMonth>EOMONTH(@FromDate)
    GROUP BY t.EmployeeCode
    ORDER BY MAX(t.FirstMonth) DESC,RampPctAt3M;

### S86 — Hợp đồng ETC chậm thực hiện, còn giá trị lớn hoặc sắp hết hạn — PARTIAL

Cho câu hỏi "hợp đồng ETC nào thực hiện chậm, còn giá trị lớn chưa giải ngân, sắp hết hạn hoặc phát
sinh công nợ quá hạn". Khác S29 (liệt kê hợp đồng) ở chỗ đối chiếu giá trị hợp đồng với DOANH THU
THỰC HIỆN và trả về tỷ lệ thực hiện cùng số ngày còn lại.

Một checker này phục vụ cả C44 và M42 — hai câu hỏi cùng nội dung, khác phạm vi (`@AreaCode`).

**PARTIAL**:
- Ghép hợp đồng với hóa đơn qua `CustomerCode` + `ItemCode` trong khoảng hiệu lực. Nếu Bravo có khóa
  hợp đồng trên hóa đơn thì phải dùng khóa đó — ghép theo khách/mặt hàng sẽ nhận nhầm doanh thu
  ngoài hợp đồng của cùng khách.
- Cột công nợ quá hạn để trống, ghép từ `usp_DeptAccDueDate_GetData` — không tự tính (xem S83).
- Tỷ lệ trúng thầu vẫn chưa map được trạng thái, giữ nguyên ghi chú ở S29.

    WITH h AS (
      SELECT h.Id0 ContractId,MAX(h.DocNo0) ContractNo,MAX(h.CustomerCode) CustomerCode,
             MAX(h.FromDate0) FromDate,MAX(h.ToDate0) ToDate,MAX(h.StatusId) StatusId,
             SUM(h.AmountBefVat) ContractValue
      FROM dbo.vHopDongETC h GROUP BY h.Id0
    ), used AS (
      SELECT c.ContractId,SUM(s.Amount9) DeliveredRevenue
      FROM (SELECT h.Id0 ContractId,h.CustomerCode,h.ItemCode,h.FromDate0,h.ToDate0
            FROM dbo.vHopDongETC h) c
      JOIN #sales s ON s.CustomerCode=c.CustomerCode AND s.ItemCode=c.ItemCode
        AND s.DocDate>=c.FromDate0 AND s.DocDate<=c.ToDate0 AND s.Channel='ETC'
      GROUP BY c.ContractId
    )
    SELECT h.ContractId,h.ContractNo,h.CustomerCode,h.FromDate,h.ToDate,h.StatusId,
           h.ContractValue,ISNULL(u.DeliveredRevenue,0) DeliveredRevenue,
           h.ContractValue-ISNULL(u.DeliveredRevenue,0) RemainingValue,
           100.0*ISNULL(u.DeliveredRevenue,0)/NULLIF(h.ContractValue,0) DeliveryPct,
           DATEDIFF(day,@AsOfDate,h.ToDate) DaysToExpiry,
           CAST(NULL AS decimal(18,2)) OverdueAmount,
           CASE WHEN DATEDIFF(day,@AsOfDate,h.ToDate) BETWEEN 0 AND 60
                     AND 100.0*ISNULL(u.DeliveredRevenue,0)/NULLIF(h.ContractValue,0)<70
                     THEN 'SAP_HET_HAN_CHUA_DAT'
                WHEN 100.0*ISNULL(u.DeliveredRevenue,0)/NULLIF(h.ContractValue,0)<50
                     THEN 'THUC_HIEN_CHAM'
                ELSE 'BINH_THUONG' END ContractFlag
    FROM h LEFT JOIN used u ON u.ContractId=h.ContractId
    WHERE h.ToDate>=@FromDate
      AND h.FromDate>=@FromDate
      AND (DATEDIFF(day,@AsOfDate,h.ToDate) BETWEEN 0 AND 60
           OR 100.0*ISNULL(u.DeliveredRevenue,0)/NULLIF(h.ContractValue,0)<50)
    ORDER BY RemainingValue DESC;

Chỉ trả hợp đồng CÓ VẤN ĐỀ: sắp hết hạn trong 60 ngày, hoặc mới thực hiện dưới 50%. Bản chạy
28/08/2026 trả cả hợp đồng `BINH_THUONG` nên ra 3.537 dòng — câu hỏi hỏi "hợp đồng nào chậm" mà trả
về toàn bộ danh mục thì người đọc vẫn phải tự lọc.

Điều kiện `h.FromDate>=@FromDate` là bắt buộc, không phải để cắt bớt dòng: `#sales` chỉ chứa hóa đơn
từ `@FromDate`, nên hợp đồng bắt đầu TRƯỚC đó bị mất phần giao hàng nằm ngoài cửa sổ. Bản chạy
28/08/2026 có hợp đồng `120270` hiệu lực từ 10/01/2024 ra `DeliveryPct = 0,08%` và bị gán nhãn
"thực hiện chậm", trong khi thực chất là **không đo được**. Gọi nhầm "không đo được" thành "chậm"
là bịa số. Muốn đo đúng nhóm này thì phải mở rộng `@FromDate` của `#sales` về trước ngày hiệu lực
hợp đồng, hoặc dùng khóa hợp đồng trên hóa đơn nếu Bravo có.

Số hợp đồng bị loại vì không đo được, để con số đó nhìn thấy được thay vì biến mất:

    SELECT COUNT(*) ContractsKhongDoDuoc,
           SUM(x.ContractValue) GiaTriKhongDoDuoc,
           MIN(x.FromDate) HopDongSomNhat
    FROM (
      SELECT h.Id0 ContractId,MAX(h.FromDate0) FromDate,MAX(h.ToDate0) ToDate,
             SUM(h.AmountBefVat) ContractValue
      FROM dbo.vHopDongETC h GROUP BY h.Id0
    ) x
    WHERE x.ToDate>=@FromDate AND x.FromDate<@FromDate;

## 4. Mapping từng câu hỏi → SQL checker

| Câu | Nội dung | Checker | Trạng thái |
|---|---|---|---|
| C01 | Doanh thu thuần từng tháng 24 tháng gần nhất của toàn công ty, OTC và ETC là bao nhiêu; MoM, YoY và CAGR/nhịp tăng trưởng thế nào? | S01 | READY |
| C02 | Mỗi tháng đạt bao nhiêu phần trăm kế hoạch; thiếu/vượt bao nhiêu tiền theo toàn công ty, kênh và miền? | S02 | PARTIAL |
| C03 | Lũy kế YTD thực hiện so kế hoạch và cùng kỳ năm trước thế nào; cần bình quân bao nhiêu mỗi tháng còn lại để đạt kế hoạch năm? | S79 | PARTIAL |
| C04 | Run-rate tháng hiện tại đang hướng tới mức nào; kênh/miền nào tạo rủi ro hụt kế hoạch cuối tháng? | S03 | DERIVED |
| C05 | Tăng/giảm doanh thu tháng này so tháng trước và cùng kỳ đến từ kênh, miền, vùng nào; mỗi đơn vị đóng góp bao nhiêu vào biến động chung? | S04 | DERIVED |
| C06 | Biến động doanh thu được giải thích bao nhiêu bởi số đơn, số khách mua, tần suất mua, sản lượng, giá bán và cơ cấu sản phẩm? | S05 | DERIVED |
| C07 | Trung bình trượt 3 tháng và 6 tháng đang tăng hay giảm; có điểm gãy xu hướng ở tháng nào? | S06 | DERIVED |
| C08 | Những tháng có tính mùa vụ cao/thấp nhất theo kênh và nhóm sản phẩm là tháng nào; tháng hiện tại lệch mô hình mùa vụ bao nhiêu? | S80 | PARTIAL |
| C09 | Giá trị đơn hàng bình quân, số đơn và doanh thu/khách hoạt động thay đổi month-by-month ra sao? | S07 | READY |
| C10 | Tỷ trọng OTC/ETC thay đổi thế nào qua từng tháng; sự thay đổi cơ cấu làm tăng hay giảm tốc độ tăng trưởng chung? | S08 | READY |
| C11 | Doanh thu đang phụ thuộc vào top 10 khách hàng, top 10 sản phẩm và top 3 miền/vùng ở mức nào; xu hướng tập trung tăng hay giảm? | S70 | READY |
| C12 | Nếu loại các giao dịch bất thường, đơn lớn đột biến, trả hàng và điều chỉnh, tăng trưởng cốt lõi từng tháng còn bao nhiêu? | S09 | READY |
| C13 | Doanh thu gộp, chiết khấu, khuyến mãi, hàng trả và doanh thu thuần từng tháng là bao nhiêu? | S10 | BLOCKED |
| C14 | Lợi nhuận gộp và biên lợi nhuận gộp theo tháng, kênh, miền và nhóm sản phẩm thay đổi thế nào? | S10 | BLOCKED |
| C15 | Kênh/miền/sản phẩm nào tăng doanh thu nhưng giảm biên lợi nhuận; nguyên nhân do giá, chiết khấu, giá vốn hay cơ cấu? | S10 | BLOCKED |
| C16 | Giá bán thực tế bình quân của từng SKU thay đổi MoM/YoY ra sao; SKU nào có dấu hiệu giảm giá hoặc xói mòn giá? | S11 | READY |
| C17 | Tỷ lệ hàng trả/điều chỉnh trên doanh thu theo tháng và kênh là bao nhiêu; nơi nào vượt ngưỡng? | S77 | READY |
| C18 | Chi phí khuyến mãi/chiết khấu tạo thêm bao nhiêu doanh thu và lợi nhuận; chương trình nào thực sự có uplift so baseline? | S12 | PARTIAL |
| C19 | Sản phẩm/khách hàng nào doanh thu cao nhưng lợi nhuận thấp hoặc âm; tỷ trọng của nhóm này tăng hay giảm? | S10 | BLOCKED |
| C20 | Tăng trưởng trên cùng tập khách hàng và cùng tập sản phẩm (like-for-like) là bao nhiêu, tách khỏi tăng trưởng do mở mới? | S13 | DERIVED |
| C21 | Xếp hạng kênh, miền, vùng, tỉnh và chi nhánh/NPP theo doanh thu, tăng trưởng, % kế hoạch và đóng góp tăng trưởng từng tháng. | S14 | READY |
| C22 | Đơn vị nào tăng trưởng liên tục 3/6 tháng; đơn vị nào giảm liên tục 3/6 tháng? | S49 | READY |
| C23 | Địa bàn nào có quy mô lớn nhưng tăng trưởng thấp; địa bàn nào quy mô nhỏ nhưng đang tăng nhanh? | S50 | READY |
| C24 | Tỉnh/vùng nào có độ phủ khách hàng thấp so với các địa bàn tương đồng; cơ hội trắng nằm ở đâu? | S51 | READY |
| C25 | Năng suất mỗi NPP/chi nhánh theo tháng là bao nhiêu; NPP nào doanh thu giảm, tồn kho tăng hoặc công nợ xấu đi? | S15 | READY |
| C26 | Khách mua đồng thời OTC và ETC đóng góp bao nhiêu doanh thu/công nợ; xu hướng mua chéo kênh ra sao? | S16 | READY |
| C27 | Có sự dịch chuyển doanh thu bất thường giữa kênh, miền, chi nhánh hoặc mã nhân viên qua các tháng không? | S17 | PARTIAL |
| C28 | Nếu loại ảnh hưởng của thay đổi địa bàn, chuyển nhân viên và chuyển khách, tăng trưởng thực của từng đơn vị còn bao nhiêu? | S17 | PARTIAL |
| C29 | Số khách hoạt động, khách mới, khách mua lại, khách tái kích hoạt và khách ngừng mua từng tháng là bao nhiêu? | S18 | READY |
| C30 | Tỷ lệ giữ chân khách theo cohort tháng mở mới sau 1/3/6/12 tháng là bao nhiêu, theo kênh và miền? | S19 | DERIVED |
| C31 | Doanh thu mất đi từ khách ngừng mua và doanh thu tăng thêm từ khách mới/tái kích hoạt bù được bao nhiêu? | S20 | READY |
| C32 | Top khách hàng tăng/giảm mạnh nhất từng tháng là ai; thay đổi đó ảnh hưởng bao nhiêu đến toàn công ty? | S71 | READY |
| C33 | Nhóm sản phẩm/SKU nào là động lực tăng trưởng, nhóm nào kéo giảm tăng trưởng và nhóm nào mất thị phần nội bộ? | S21 | READY |
| C34 | Doanh thu sản phẩm mới sau 1/3/6/12 tháng ra mắt đạt bao nhiêu so kế hoạch; độ phủ khách hàng ra sao? | S22 | DERIVED |
| C35 | Mức độ phụ thuộc vào sản phẩm chủ lực qua từng tháng; nếu top 1/top 5 giảm 20% thì doanh thu bị ảnh hưởng bao nhiêu? | S23 | DERIVED |
| C36 | SKU nào có độ phủ khách hàng tăng nhưng doanh thu/khách giảm, hoặc doanh thu tăng nhưng độ phủ co lại? | S73 | DERIVED |
| C37 | Dư nợ, nợ quá hạn, tỷ lệ quá hạn và cơ cấu tuổi nợ month-by-month theo kênh/miền thay đổi thế nào? | S25 | BLOCKED_HISTORY |
| C38 | Thu tiền trong tháng so với doanh thu và kế hoạch thu tiền là bao nhiêu; DSO và vòng quay công nợ thay đổi ra sao? | S45 | BLOCKED_HISTORY |
| C39 | Khách nào đồng thời doanh thu giảm, nợ quá hạn tăng và tuổi nợ xấu đi qua 2–3 tháng? | S26 | PARTIAL |
| C40 | Top khách nợ chiếm bao nhiêu phần trăm tổng nợ; rủi ro tập trung công nợ tăng hay giảm? | S24 | READY_CURRENT |
| C41 | Giá trị tồn kho, số tháng tồn, hàng chậm luân chuyển, stock-out và hàng cận date thay đổi thế nào theo tháng? | S27 | READY_CURRENT |
| C42 | SKU nào mất doanh số do thiếu hàng; SKU nào tồn cao trong khi doanh số giảm liên tục? | S47 | DERIVED |
| C43 | Kế hoạch thầu ETC, giá trị tham gia, giá trị trúng, tỷ lệ trúng và doanh thu thực hiện theo tháng/quý là bao nhiêu? | S29 | PARTIAL |
| C44 | Hợp đồng ETC nào thực hiện chậm, còn giá trị lớn chưa giải ngân, sắp hết hạn hoặc phát sinh công nợ quá hạn? | S86 | PARTIAL |
| C45 | Tỷ lệ nhân sự đạt 65/70%, 80%, 100% và 120% KPI từng tháng theo kênh/miền/chức danh là bao nhiêu? | S30 | READY |
| C46 | Năng suất doanh thu trên đầu người và trên quản lý thay đổi thế nào; đơn vị nào tăng headcount nhưng năng suất giảm? | S32 | PARTIAL |
| C47 | Cá nhân/đội nào dưới 80% liên tiếp 3 tháng hoặc biến động mạnh; khoảng hụt doanh thu là bao nhiêu? | S64 | READY |
| C48 | Chi phí thưởng kinh doanh trên doanh thu/lợi nhuận theo tháng là bao nhiêu; cơ chế thưởng có tương quan với tăng trưởng bền vững không? | S33 | PARTIAL |
| C49 | Độ phủ tuyến, số lượt viếng thăm, tỷ lệ viếng thăm có đơn và doanh thu/lượt viếng thăm thay đổi ra sao? | S34 | READY |
| C50 | Dự báo doanh thu cuối tháng/quý theo kênh/miền là bao nhiêu; khoảng tin cậy và giả định chính là gì? | S35 | PARTIAL |
| C51 | Ba rủi ro lớn nhất khiến không đạt kế hoạch là gì; mỗi rủi ro ảnh hưởng ước tính bao nhiêu tiền? | S82 | DERIVED |
| C52 | Mỗi kênh/miền cam kết hành động gì để đóng gap; chủ sở hữu, hạn hoàn thành và kết quả tháng sau ra sao? | S36 | BLOCKED |
| C53 | Số liệu doanh thu, KPI, công nợ, tồn kho, khuyến mãi và lương đang chốt đến tháng/ngày nào; nguồn nào chưa đồng bộ? | S37 | READY |
| C54 | Chỉ tiêu nào có dấu hiệu sai do trùng tầng quản lý, thiếu mapping, thay đổi mã, thiếu target hoặc snapshot chưa chốt? | S38 | READY |
| M01 | Doanh thu từng tháng của miền/kênh tôi so kế hoạch, tháng trước, cùng kỳ và YTD thế nào? | S01 | READY |
| M02 | Gap tới kế hoạch tháng/quý còn bao nhiêu; mỗi vùng cần đóng góp thêm bao nhiêu? | S43 | PARTIAL |
| M03 | Vùng nào đóng góp nhiều nhất vào tăng/giảm của miền/kênh tháng này? | S04 | DERIVED |
| M04 | Xếp hạng các vùng theo doanh thu, tăng trưởng, % kế hoạch, lợi nhuận và công nợ; thứ hạng thay đổi ra sao 6 tháng qua? | S14 | READY |
| M05 | Vùng nào dưới 80% kế hoạch liên tiếp; tổng hụt doanh thu tích lũy là bao nhiêu? | S58 | PARTIAL |
| M06 | Doanh thu ngày/tuần trong tháng đang chạy nhanh hay chậm hơn nhịp cần thiết để đạt target? | S03 | DERIVED |
| M07 | Số khách mua, số đơn, AOV và tần suất mua của miền/kênh thay đổi thế nào qua từng tháng? | S07 | READY |
| M08 | Tăng trưởng hiện tại đến từ mở mới khách hàng hay tăng mua trên khách hàng hiện hữu? | S18 | READY |
| M09 | Đơn hàng/hóa đơn bất thường nào làm biến động kết quả tháng; nếu loại chúng thì kết quả còn bao nhiêu? | S09 | READY |
| M10 | Tỉnh/chi nhánh/NPP nào đang kéo giảm kết quả và cần ưu tiên can thiệp? | S52 | READY |
| M11 | Doanh số, target và % hoàn thành của từng QLV/đội theo tháng; ai cải thiện hoặc suy giảm mạnh nhất? | S39 | READY |
| M12 | Đội nào đạt 100%, 80%, qua cổng 65/70% hoặc dưới cổng; xu hướng 3 tháng thế nào? | S31 | READY |
| M13 | QLV nào có nhiều nhân viên dưới 80% nhất; phần hụt của đội tập trung ở ai? | S65 | READY |
| M14 | Đội nào có doanh thu cao nhưng phụ thuộc vào ít nhân viên hoặc ít khách hàng? | S54 | READY |
| M15 | Năng suất doanh thu/TDV, doanh thu/khách và doanh thu/ngày làm việc của từng đội thay đổi thế nào? | S32 | PARTIAL |
| M16 | Nhân viên nào giảm doanh số liên tiếp 3 tháng; giảm do mất khách, giảm tần suất hay giảm giá trị đơn? | S55 | READY |
| M17 | Nhân viên mới đạt ramp-up thế nào sau 1/2/3/6 tháng so với chuẩn cùng vai trò? | S85 | DERIVED |
| M18 | Địa bàn trống, nhân viên nghỉ/chuyển vùng hoặc khách chưa gán người phụ trách ảnh hưởng bao nhiêu doanh thu? | S81 | PARTIAL |
| M19 | QLV nào có span of control quá lớn/nhỏ; quy mô đội có ảnh hưởng đến năng suất không? | S66 | PARTIAL |
| M20 | Thưởng/KPI của đội có khớp doanh số và chính sách đã chốt; có bất thường nào cần kiểm tra? | S33 | PARTIAL |
| M21 | Top khách hàng theo doanh thu từng tháng; khách nào tăng/giảm mạnh và QLV nào phụ trách? | S20 | READY |
| M22 | Khách lớn nào ngừng mua, giảm mua hoặc kéo dài chu kỳ mua so với lịch sử? | S40 | READY |
| M23 | Số khách mới, tái kích hoạt, mua lại và ngừng mua của từng vùng; tỷ lệ giữ chân sau 3/6 tháng? | S67 | READY |
| M24 | Vùng nào mở nhiều khách mới nhưng doanh thu/khách và tỷ lệ mua lại thấp? | S19 | DERIVED |
| M25 | Khách nào có tiềm năng bán chéo nhóm sản phẩm do đang mua ít SKU hơn nhóm khách tương đồng? | S41 | DERIVED |
| M26 | Khách hàng nào có share-of-wallet nội bộ thấp: doanh thu lớn nhưng chỉ mua một nhóm sản phẩm? | S23 | DERIVED |
| M27 | Tỉnh/huyện nào có ít khách hoạt động, ít đơn hoặc doanh thu/khách thấp hơn chuẩn miền? | S53 | READY |
| M28 | Tỷ lệ khách không gán TDV, sai vùng hoặc thiếu thông tin DMS theo tháng là bao nhiêu? | S38 | READY |
| M29 | NPP/chi nhánh nào có tăng trưởng khách hàng tốt nhưng công nợ hoặc tồn kho xấu đi? | S15 | READY |
| M30 | Danh sách 20 khách hàng ưu tiên cần giữ, thu hồi, tái kích hoạt hoặc mở rộng trong tháng tới là ai? | S48 | DERIVED |
| M31 | Nhóm sản phẩm/SKU nào đóng góp nhiều nhất vào tăng/giảm của miền/kênh theo tháng? | S21 | READY |
| M32 | SKU chiến lược đạt bao nhiêu % target tại từng vùng; vùng nào có khoảng trống độ phủ lớn nhất? | S46 | PARTIAL |
| M33 | SKU nào doanh thu giảm do ít khách mua, ít đơn, giảm lượng/đơn hay giảm giá bán? | S72 | READY |
| M34 | Sản phẩm mới đạt độ phủ và doanh thu sau 1/3/6 tháng thế nào tại từng vùng? | S22 | DERIVED |
| M35 | Chương trình khuyến mãi nào có nhiều khách tham gia nhưng không tạo tăng trưởng; chương trình nào tạo uplift tốt? | S12 | PARTIAL |
| M36 | Tỷ lệ trả hàng, chiết khấu và hàng tặng trên doanh thu của từng vùng thay đổi ra sao? | S78 | PARTIAL |
| M37 | Tổng nợ, nợ quá hạn, DSO và thu tiền của từng vùng/QLV qua từng tháng; đơn vị nào xấu đi nhanh nhất? | S25 | BLOCKED_HISTORY |
| M38 | Khách nào cần dừng/bóp bán vì nợ xấu; doanh thu có nguy cơ ảnh hưởng là bao nhiêu? | S26 | PARTIAL |
| M39 | SKU nào thiếu hàng ở miền/kênh và làm mất doanh số; SKU nào tồn cao hơn nhu cầu 3–6 tháng? | S47 | DERIVED |
| M40 | Hàng cận date/chậm luân chuyển nào cần chuyển vùng, đẩy bán hoặc dừng nhập? | S28 | PARTIAL |
| M41 | Với ETC, kế hoạch thầu, tỷ lệ trúng, doanh thu thực hiện và thu tiền từng tháng của từng vùng/khách hàng thế nào? | S29 | PARTIAL |
| M42 | Hợp đồng/gói thầu nào có tỷ lệ thực hiện thấp, còn giá trị lớn hoặc sắp hết hiệu lực? | S86 | PARTIAL |
| M43 | Dự báo cuối tháng của từng vùng/QLV là bao nhiêu; vùng nào có xác suất không đạt cao nhất? | S35 | PARTIAL |
| M44 | Với từng vùng dưới kế hoạch: ba nguyên nhân định lượng, ba hành động, người chịu trách nhiệm và deadline là gì? | S36 | BLOCKED |
| V01 | Đội tôi đạt bao nhiêu doanh số và bao nhiêu % target tháng; MoM, YoY và YTD thế nào? | S43 | PARTIAL |
| V02 | Còn thiếu bao nhiêu để đạt 65/70%, 80%, 100% và 120%; mỗi ngày còn lại cần bán bao nhiêu? | S59 | PARTIAL |
| V03 | Doanh số từng ngày/tuần đang cao hay thấp hơn nhịp cần thiết; ngày nào không có phát sinh? | S03 | DERIVED |
| V04 | Nhân viên nào đóng góp nhiều nhất vào tăng/giảm doanh số đội tháng này? | S39 | READY |
| V05 | Nếu loại đơn hàng lớn bất thường và hàng trả, kết quả thực chất của đội là bao nhiêu? | S09 | READY |
| V06 | Doanh thu đội đến từ bao nhiêu khách, bao nhiêu đơn; AOV và tần suất mua thay đổi thế nào? | S07 | READY |
| V07 | So với 3 tháng gần nhất, tháng này đội giảm ở số khách, số đơn, sản lượng hay giá trị đơn? | S05 | DERIVED |
| V08 | Tỉnh/địa bàn con nào đang dưới kế hoạch; phần hụt là bao nhiêu và TDV nào phụ trách? | S60 | PARTIAL |
| V09 | Dự báo cuối tháng của đội theo run-rate hiện tại; kịch bản cơ sở/tốt/xấu là bao nhiêu? | S35 | PARTIAL |
| V10 | Hôm nay/tuần này cần ưu tiên khách hàng, sản phẩm và nhân viên nào để đóng gap lớn nhất? | S84 | READY |
| V11 | Doanh số, target và % hoàn thành từng TDV theo tháng; xếp hạng và xu hướng 3/6 tháng? | S56 | READY |
| V12 | Ai dưới 65/70%, dưới 80%, đạt 100% hoặc vượt 120%; mỗi người còn thiếu bao nhiêu tiền? | S31 | READY |
| V13 | Ai giảm liên tiếp 2–3 tháng; nguyên nhân nằm ở khách mất, ít đơn, ít SKU hay giá trị đơn giảm? | S57 | READY |
| V14 | Ai có nhiều khách phụ trách nhưng tỷ lệ khách mua thấp; ai có ít khách nhưng doanh thu/khách cao? | S44 | READY |
| V15 | Ai mở nhiều khách mới nhưng tỷ lệ mua lại thấp; ai tái kích hoạt khách tốt nhất? | S61 | READY |
| V16 | Ai có ngày làm việc/đi tuyến nhưng không phát sinh đơn; tỷ lệ viếng thăm có đơn là bao nhiêu? | S34 | READY |
| V17 | Nhân viên nào có doanh số nhưng thiếu target, thiếu manager, sai địa bàn hoặc trùng mã? | S38 | READY |
| V18 | Thưởng và phụ cấp từng người thay đổi thế nào; có điểm nào không khớp KPI/chính sách? | S33 | PARTIAL |
| V19 | Top khách hàng đội tôi từng tháng là ai; khách nào tăng/giảm mạnh nhất? | S20 | READY |
| V20 | Khách đã mua tháng trước nhưng chưa mua tháng này là ai; doanh thu có nguy cơ mất bao nhiêu? | S40 | READY |
| V21 | Khách im lặng 30/60/90 ngày là ai; lần mua gần nhất, giá trị và sản phẩm thường mua là gì? | S69 | READY |
| V22 | Khách mới tháng này là ai; đã có đơn lặp lại chưa và TDV nào phụ trách? | S18 | READY |
| V23 | Khách mua lại/tái kích hoạt là ai; doanh thu phục hồi so trước khi ngừng mua thế nào? | S68 | READY |
| V24 | Khách nào giảm tần suất mua, AOV hoặc số SKU/đơn so với 3 tháng trước? | S62 | READY |
| V25 | Khách nào chỉ mua một nhóm sản phẩm và có cơ hội bán chéo rõ nhất? | S41 | DERIVED |
| V26 | Khách nào mua ít hơn các khách tương đồng cùng tỉnh/phân khúc? | S63 | READY |
| V27 | Khách nào chưa gán TDV, sai mã, sai tỉnh/vùng hoặc không có tên trong DMS? | S75 | READY |
| V28 | Danh sách khách ưu tiên tuần này theo bốn mục tiêu: giữ khách lớn, tái kích hoạt, thu nợ và bán chéo? | S83 | PARTIAL |
| V29 | Top/bottom sản phẩm từng tháng của đội; SKU nào làm tăng/giảm doanh số nhiều nhất? | S21 | READY |
| V30 | SKU trọng tâm đạt bao nhiêu % target theo từng TDV và khách hàng; khoảng thiếu bao nhiêu? | S46 | PARTIAL |
| V31 | Sản phẩm nào nhiều khách mua nhưng lượng/đơn thấp; sản phẩm nào ít khách nhưng AOV cao? | S23 | DERIVED |
| V32 | Cặp sản phẩm nào thường mua cùng; khách nào phù hợp bán combo nhưng chưa mua? | S74 | DERIVED |
| V33 | Đơn nào bị hủy, trả, điều chỉnh, giao/hóa đơn chậm hoặc chưa tìm thấy hóa đơn? | S42 | READY |
| V34 | Chương trình khuyến mãi nào đội đang dùng; khách tham gia, số đơn và doanh thu trước–trong–sau chương trình thế nào? | S12 | PARTIAL |
| V35 | Tổng nợ và nợ quá hạn của đội theo tháng; khách nào mới chuyển sang nhóm tuổi nợ xấu hơn? | S25 | BLOCKED_HISTORY |
| V36 | Khách nào vừa nợ quá hạn vừa giảm mua; TDV phụ trách và số tiền cần thu là bao nhiêu? | S26 | PARTIAL |
| V37 | Thu tiền tháng này của từng TDV/khách so kế hoạch; cam kết thu nào đã quá hạn? | S45 | BLOCKED_HISTORY |
| V38 | SKU khách đang cần nhưng kho thiếu là gì; đơn/doanh thu nào có nguy cơ mất vì thiếu hàng? | S47 | DERIVED |
| V39 | SKU tồn cao/chậm bán/cận date trong phạm vi vùng là gì; khách nào phù hợp để xử lý tồn? | S28 | PARTIAL |
| V40 | Cuối tháng, những ngoại lệ nào chưa xử lý: target thiếu, khách chưa gán, đơn chưa hóa đơn, nợ xấu, hàng trả và dữ liệu chưa đồng bộ? | S76 | READY |

## 5. Các nguyên tắc pass/fail bắt buộc

1. Tổng theo kênh/miền/vùng phải khớp tổng công ty; khách chưa map phải vào CHUA_XAC_DINH.
2. Không cộng doanh số ở nhiều tầng TP–QLV–TDV vì là số roll-up chồng nhau.
3. Target ở FACT_TongHopKhachHang dùng MAX theo nhân viên/snapshot, không SUM theo khách.
4. Số đơn dùng khóa Channel + Stt; không trộn Stt giống nhau giữa OTC và ETC.
5. Sản lượng bán thật chỉ tính UnitPrice > 0; hàng tặng không nhập vào paid quantity.
6. Associated revenue của CTKM không cộng ngang giữa chương trình vì một đơn có thể gắn nhiều CTKM.
7. Công nợ chỉ dùng SP usp_DeptAccDueDate_GetData/kho fact_congno_khachhang; không dùng Excel cũ.
8. Checker BLOCKED/PARTIAL không được trả lời như đã có số đầy đủ.
9. Mọi câu month-by-month phải công bố khoảng lịch sử thực có và mốc đồng bộ từng nguồn.
10. SQL này là catalog đối soát read-oriented; chưa được coi là định nghĩa KPI chính thức nếu còn nhãn DERIVED.
