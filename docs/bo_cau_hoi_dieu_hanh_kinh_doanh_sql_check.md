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

## 2. Tham số và lớp bán hàng chuẩn

Chạy block này một lần trong cùng session trước các checker dùng #sales. Chỉ tạo bảng tạm trong
tempdb, không ghi vào dữ liệu DNH.

    DECLARE @FromDate date = '2025-09-01';
    DECLARE @ToDate date = '2026-09-01';
    DECLARE @MonthStart date = '2026-08-01';
    DECLARE @MonthEnd date = DATEADD(month, 1, @MonthStart);
    DECLARE @AsOfDate date = DATEADD(day, -1, @MonthEnd);
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
               CustomerCode, ItemCode, GroupCode, BranchCode, DistributorCode,
               EmpDMSCode, Quantity, UnitPrice, Amount9, DocCode, DMSId
        FROM dbo.vHoaDonTotal
        WHERE DocDate >= @FromDate AND DocDate < @ToDate
        UNION ALL
        SELECT 'ETC', DocDate, CONCAT('ETC|', Stt), Stt,
               CustomerCode, ItemCode, GroupCode, BranchCode, DistributorCode,
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

### S01 — Doanh thu tháng, MoM, YoY và YTD — READY

    WITH m AS (
      SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,Channel,
             SUM(Amount9) Revenue,COUNT(DISTINCT OrderKey) Orders,
             COUNT(DISTINCT CustomerCode) ActiveCustomers
      FROM #sales GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1),Channel
    )
    SELECT MonthStart,Channel,Revenue,Orders,ActiveCustomers,
           Revenue-LAG(Revenue) OVER(PARTITION BY Channel ORDER BY MonthStart) MoMDelta,
           100.0*(Revenue-LAG(Revenue) OVER(PARTITION BY Channel ORDER BY MonthStart))
             /NULLIF(LAG(Revenue) OVER(PARTITION BY Channel ORDER BY MonthStart),0) MoMPct,
           Revenue-LAG(Revenue,12) OVER(PARTITION BY Channel ORDER BY MonthStart) YoYDelta
    FROM m ORDER BY MonthStart,Channel;

### S02 — Thực hiện so target tháng/YTD — PARTIAL

Chỉ cộng tầng nhân viên tuyến dưới để tránh trùng roll-up. Target ETC toàn kênh phải map riêng.

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate) ORDER BY SaveDate DESC) SnapshotRank
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
    SELECT MonthEnd,COUNT(*) DualChannelCustomers,SUM(Revenue) Revenue
    FROM c WHERE Channels=2 GROUP BY MonthEnd ORDER BY MonthEnd;

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

    EXEC dbo.usp_DeptAccDueDate_GetData
      @_DocDate1=DATEFROMPARTS(YEAR(@AsOfDate),1,1),
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
        PARTITION BY EOMONTH(SaveDate) ORDER BY SaveDate DESC) SnapshotRank
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
        PARTITION BY EOMONTH(SaveDate) ORDER BY SaveDate DESC) SnapshotRank
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
        PARTITION BY EOMONTH(SaveDate) ORDER BY SaveDate DESC) SnapshotRank
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
        PARTITION BY EOMONTH(SaveDate) ORDER BY SaveDate DESC) SnapshotRank
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
    ), t AS (
      SELECT SUM(MonthSaleTarget) Target
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate=(SELECT MAX(SaveDate) FROM dbo.FACT_ThongKeTinhLuong WHERE SaveDate<=@AsOfDate)
        AND PositionCode IN ('TDV','CTV','CS')
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
        AND (@ManagerCode IS NULL OR ManagerCode=@ManagerCode)
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
    SELECT p.A,p.B,l.CustomerCode,p.Together
    FROM pairs p JOIN l ON l.ItemCode=p.A
    WHERE NOT EXISTS(SELECT 1 FROM l x WHERE x.CustomerCode=l.CustomerCode AND x.ItemCode=p.B);

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

    WITH e AS (
      SELECT EmployeeCode,MAX(ManagerCode) ManagerCode,SUM(Amount_CT) Actual,MAX(MonthSaleTarget) Target
      FROM dbo.FACT_TongHopKhachHang
      WHERE SaveDate=(SELECT MAX(SaveDate) FROM dbo.FACT_TongHopKhachHang WHERE SaveDate<=@AsOfDate)
        AND (@ManagerCode IS NULL OR ManagerCode=@ManagerCode)
      GROUP BY EmployeeCode
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
    SELECT EOMONTH(f.SaveDate) MonthEnd,f.AreaCode,f.ManagerCode,f.EmployeeCode,f.GroupCode,f.ItemCode,
           MAX(IsTargetProduct) IsTargetProduct,COUNT(*) FactRows
    FROM dbo.FACT_TongHopSanPham f JOIN snaps s ON s.SaveDate=f.SaveDate
    WHERE (@AreaCode IS NULL OR f.AreaCode=@AreaCode)
      AND (@ManagerCode IS NULL OR f.ManagerCode=@ManagerCode)
    GROUP BY EOMONTH(f.SaveDate),f.AreaCode,f.ManagerCode,f.EmployeeCode,f.GroupCode,f.ItemCode;

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

## 4. Mapping từng câu hỏi → SQL checker

| Câu | Nội dung | Checker | Trạng thái |
|---|---|---|---|
| C01 | Doanh thu thuần từng tháng 24 tháng gần nhất của toàn công ty, OTC và ETC là bao nhiêu; MoM, YoY và CAGR/nhịp tăng trưởng thế nào? | S01 | READY |
| C02 | Mỗi tháng đạt bao nhiêu phần trăm kế hoạch; thiếu/vượt bao nhiêu tiền theo toàn công ty, kênh và miền? | S02 | PARTIAL |
| C03 | Lũy kế YTD thực hiện so kế hoạch và cùng kỳ năm trước thế nào; cần bình quân bao nhiêu mỗi tháng còn lại để đạt kế hoạch năm? | S02 | PARTIAL |
| C04 | Run-rate tháng hiện tại đang hướng tới mức nào; kênh/miền nào tạo rủi ro hụt kế hoạch cuối tháng? | S03 | DERIVED |
| C05 | Tăng/giảm doanh thu tháng này so tháng trước và cùng kỳ đến từ kênh, miền, vùng nào; mỗi đơn vị đóng góp bao nhiêu vào biến động chung? | S04 | DERIVED |
| C06 | Biến động doanh thu được giải thích bao nhiêu bởi số đơn, số khách mua, tần suất mua, sản lượng, giá bán và cơ cấu sản phẩm? | S05 | DERIVED |
| C07 | Trung bình trượt 3 tháng và 6 tháng đang tăng hay giảm; có điểm gãy xu hướng ở tháng nào? | S06 | DERIVED |
| C08 | Những tháng có tính mùa vụ cao/thấp nhất theo kênh và nhóm sản phẩm là tháng nào; tháng hiện tại lệch mô hình mùa vụ bao nhiêu? | S06 | DERIVED |
| C09 | Giá trị đơn hàng bình quân, số đơn và doanh thu/khách hoạt động thay đổi month-by-month ra sao? | S07 | READY |
| C10 | Tỷ trọng OTC/ETC thay đổi thế nào qua từng tháng; sự thay đổi cơ cấu làm tăng hay giảm tốc độ tăng trưởng chung? | S08 | READY |
| C11 | Doanh thu đang phụ thuộc vào top 10 khách hàng, top 10 sản phẩm và top 3 miền/vùng ở mức nào; xu hướng tập trung tăng hay giảm? | S08 | READY |
| C12 | Nếu loại các giao dịch bất thường, đơn lớn đột biến, trả hàng và điều chỉnh, tăng trưởng cốt lõi từng tháng còn bao nhiêu? | S09 | READY |
| C13 | Doanh thu gộp, chiết khấu, khuyến mãi, hàng trả và doanh thu thuần từng tháng là bao nhiêu? | S10 | BLOCKED |
| C14 | Lợi nhuận gộp và biên lợi nhuận gộp theo tháng, kênh, miền và nhóm sản phẩm thay đổi thế nào? | S10 | BLOCKED |
| C15 | Kênh/miền/sản phẩm nào tăng doanh thu nhưng giảm biên lợi nhuận; nguyên nhân do giá, chiết khấu, giá vốn hay cơ cấu? | S10 | BLOCKED |
| C16 | Giá bán thực tế bình quân của từng SKU thay đổi MoM/YoY ra sao; SKU nào có dấu hiệu giảm giá hoặc xói mòn giá? | S11 | READY |
| C17 | Tỷ lệ hàng trả/điều chỉnh trên doanh thu theo tháng và kênh là bao nhiêu; nơi nào vượt ngưỡng? | S09 | READY |
| C18 | Chi phí khuyến mãi/chiết khấu tạo thêm bao nhiêu doanh thu và lợi nhuận; chương trình nào thực sự có uplift so baseline? | S12 | PARTIAL |
| C19 | Sản phẩm/khách hàng nào doanh thu cao nhưng lợi nhuận thấp hoặc âm; tỷ trọng của nhóm này tăng hay giảm? | S10 | BLOCKED |
| C20 | Tăng trưởng trên cùng tập khách hàng và cùng tập sản phẩm (like-for-like) là bao nhiêu, tách khỏi tăng trưởng do mở mới? | S13 | DERIVED |
| C21 | Xếp hạng kênh, miền, vùng, tỉnh và chi nhánh/NPP theo doanh thu, tăng trưởng, % kế hoạch và đóng góp tăng trưởng từng tháng. | S14 | READY |
| C22 | Đơn vị nào tăng trưởng liên tục 3/6 tháng; đơn vị nào giảm liên tục 3/6 tháng? | S14 | READY |
| C23 | Địa bàn nào có quy mô lớn nhưng tăng trưởng thấp; địa bàn nào quy mô nhỏ nhưng đang tăng nhanh? | S14 | READY |
| C24 | Tỉnh/vùng nào có độ phủ khách hàng thấp so với các địa bàn tương đồng; cơ hội trắng nằm ở đâu? | S14 | READY |
| C25 | Năng suất mỗi NPP/chi nhánh theo tháng là bao nhiêu; NPP nào doanh thu giảm, tồn kho tăng hoặc công nợ xấu đi? | S15 | READY |
| C26 | Khách mua đồng thời OTC và ETC đóng góp bao nhiêu doanh thu/công nợ; xu hướng mua chéo kênh ra sao? | S16 | READY |
| C27 | Có sự dịch chuyển doanh thu bất thường giữa kênh, miền, chi nhánh hoặc mã nhân viên qua các tháng không? | S17 | PARTIAL |
| C28 | Nếu loại ảnh hưởng của thay đổi địa bàn, chuyển nhân viên và chuyển khách, tăng trưởng thực của từng đơn vị còn bao nhiêu? | S17 | PARTIAL |
| C29 | Số khách hoạt động, khách mới, khách mua lại, khách tái kích hoạt và khách ngừng mua từng tháng là bao nhiêu? | S18 | READY |
| C30 | Tỷ lệ giữ chân khách theo cohort tháng mở mới sau 1/3/6/12 tháng là bao nhiêu, theo kênh và miền? | S19 | DERIVED |
| C31 | Doanh thu mất đi từ khách ngừng mua và doanh thu tăng thêm từ khách mới/tái kích hoạt bù được bao nhiêu? | S20 | READY |
| C32 | Top khách hàng tăng/giảm mạnh nhất từng tháng là ai; thay đổi đó ảnh hưởng bao nhiêu đến toàn công ty? | S20 | READY |
| C33 | Nhóm sản phẩm/SKU nào là động lực tăng trưởng, nhóm nào kéo giảm tăng trưởng và nhóm nào mất thị phần nội bộ? | S21 | READY |
| C34 | Doanh thu sản phẩm mới sau 1/3/6/12 tháng ra mắt đạt bao nhiêu so kế hoạch; độ phủ khách hàng ra sao? | S22 | DERIVED |
| C35 | Mức độ phụ thuộc vào sản phẩm chủ lực qua từng tháng; nếu top 1/top 5 giảm 20% thì doanh thu bị ảnh hưởng bao nhiêu? | S23 | DERIVED |
| C36 | SKU nào có độ phủ khách hàng tăng nhưng doanh thu/khách giảm, hoặc doanh thu tăng nhưng độ phủ co lại? | S23 | DERIVED |
| C37 | Dư nợ, nợ quá hạn, tỷ lệ quá hạn và cơ cấu tuổi nợ month-by-month theo kênh/miền thay đổi thế nào? | S25 | BLOCKED_HISTORY |
| C38 | Thu tiền trong tháng so với doanh thu và kế hoạch thu tiền là bao nhiêu; DSO và vòng quay công nợ thay đổi ra sao? | S45 | BLOCKED_HISTORY |
| C39 | Khách nào đồng thời doanh thu giảm, nợ quá hạn tăng và tuổi nợ xấu đi qua 2–3 tháng? | S26 | PARTIAL |
| C40 | Top khách nợ chiếm bao nhiêu phần trăm tổng nợ; rủi ro tập trung công nợ tăng hay giảm? | S24 | READY_CURRENT |
| C41 | Giá trị tồn kho, số tháng tồn, hàng chậm luân chuyển, stock-out và hàng cận date thay đổi thế nào theo tháng? | S28 | PARTIAL |
| C42 | SKU nào mất doanh số do thiếu hàng; SKU nào tồn cao trong khi doanh số giảm liên tục? | S47 | DERIVED |
| C43 | Kế hoạch thầu ETC, giá trị tham gia, giá trị trúng, tỷ lệ trúng và doanh thu thực hiện theo tháng/quý là bao nhiêu? | S29 | PARTIAL |
| C44 | Hợp đồng ETC nào thực hiện chậm, còn giá trị lớn chưa giải ngân, sắp hết hạn hoặc phát sinh công nợ quá hạn? | S29 | PARTIAL |
| C45 | Tỷ lệ nhân sự đạt 65/70%, 80%, 100% và 120% KPI từng tháng theo kênh/miền/chức danh là bao nhiêu? | S31 | READY |
| C46 | Năng suất doanh thu trên đầu người và trên quản lý thay đổi thế nào; đơn vị nào tăng headcount nhưng năng suất giảm? | S32 | PARTIAL |
| C47 | Cá nhân/đội nào dưới 80% liên tiếp 3 tháng hoặc biến động mạnh; khoảng hụt doanh thu là bao nhiêu? | S31 | READY |
| C48 | Chi phí thưởng kinh doanh trên doanh thu/lợi nhuận theo tháng là bao nhiêu; cơ chế thưởng có tương quan với tăng trưởng bền vững không? | S33 | PARTIAL |
| C49 | Độ phủ tuyến, số lượt viếng thăm, tỷ lệ viếng thăm có đơn và doanh thu/lượt viếng thăm thay đổi ra sao? | S34 | READY |
| C50 | Dự báo doanh thu cuối tháng/quý theo kênh/miền là bao nhiêu; khoảng tin cậy và giả định chính là gì? | S35 | PARTIAL |
| C51 | Ba rủi ro lớn nhất khiến không đạt kế hoạch là gì; mỗi rủi ro ảnh hưởng ước tính bao nhiêu tiền? | S35 | PARTIAL |
| C52 | Mỗi kênh/miền cam kết hành động gì để đóng gap; chủ sở hữu, hạn hoàn thành và kết quả tháng sau ra sao? | S36 | BLOCKED |
| C53 | Số liệu doanh thu, KPI, công nợ, tồn kho, khuyến mãi và lương đang chốt đến tháng/ngày nào; nguồn nào chưa đồng bộ? | S37 | READY |
| C54 | Chỉ tiêu nào có dấu hiệu sai do trùng tầng quản lý, thiếu mapping, thay đổi mã, thiếu target hoặc snapshot chưa chốt? | S38 | READY |
| M01 | Doanh thu từng tháng của miền/kênh tôi so kế hoạch, tháng trước, cùng kỳ và YTD thế nào? | S01 | READY |
| M02 | Gap tới kế hoạch tháng/quý còn bao nhiêu; mỗi vùng cần đóng góp thêm bao nhiêu? | S43 | PARTIAL |
| M03 | Vùng nào đóng góp nhiều nhất vào tăng/giảm của miền/kênh tháng này? | S04 | DERIVED |
| M04 | Xếp hạng các vùng theo doanh thu, tăng trưởng, % kế hoạch, lợi nhuận và công nợ; thứ hạng thay đổi ra sao 6 tháng qua? | S14 | READY |
| M05 | Vùng nào dưới 80% kế hoạch liên tiếp; tổng hụt doanh thu tích lũy là bao nhiêu? | S43 | PARTIAL |
| M06 | Doanh thu ngày/tuần trong tháng đang chạy nhanh hay chậm hơn nhịp cần thiết để đạt target? | S03 | DERIVED |
| M07 | Số khách mua, số đơn, AOV và tần suất mua của miền/kênh thay đổi thế nào qua từng tháng? | S07 | READY |
| M08 | Tăng trưởng hiện tại đến từ mở mới khách hàng hay tăng mua trên khách hàng hiện hữu? | S18 | READY |
| M09 | Đơn hàng/hóa đơn bất thường nào làm biến động kết quả tháng; nếu loại chúng thì kết quả còn bao nhiêu? | S09 | READY |
| M10 | Tỉnh/chi nhánh/NPP nào đang kéo giảm kết quả và cần ưu tiên can thiệp? | S14 | READY |
| M11 | Doanh số, target và % hoàn thành của từng QLV/đội theo tháng; ai cải thiện hoặc suy giảm mạnh nhất? | S39 | READY |
| M12 | Đội nào đạt 100%, 80%, qua cổng 65/70% hoặc dưới cổng; xu hướng 3 tháng thế nào? | S31 | READY |
| M13 | QLV nào có nhiều nhân viên dưới 80% nhất; phần hụt của đội tập trung ở ai? | S31 | READY |
| M14 | Đội nào có doanh thu cao nhưng phụ thuộc vào ít nhân viên hoặc ít khách hàng? | S39 | READY |
| M15 | Năng suất doanh thu/TDV, doanh thu/khách và doanh thu/ngày làm việc của từng đội thay đổi thế nào? | S32 | PARTIAL |
| M16 | Nhân viên nào giảm doanh số liên tiếp 3 tháng; giảm do mất khách, giảm tần suất hay giảm giá trị đơn? | S39 | READY |
| M17 | Nhân viên mới đạt ramp-up thế nào sau 1/2/3/6 tháng so với chuẩn cùng vai trò? | S32 | PARTIAL |
| M18 | Địa bàn trống, nhân viên nghỉ/chuyển vùng hoặc khách chưa gán người phụ trách ảnh hưởng bao nhiêu doanh thu? | S17 | PARTIAL |
| M19 | QLV nào có span of control quá lớn/nhỏ; quy mô đội có ảnh hưởng đến năng suất không? | S32 | PARTIAL |
| M20 | Thưởng/KPI của đội có khớp doanh số và chính sách đã chốt; có bất thường nào cần kiểm tra? | S33 | PARTIAL |
| M21 | Top khách hàng theo doanh thu từng tháng; khách nào tăng/giảm mạnh và QLV nào phụ trách? | S20 | READY |
| M22 | Khách lớn nào ngừng mua, giảm mua hoặc kéo dài chu kỳ mua so với lịch sử? | S40 | READY |
| M23 | Số khách mới, tái kích hoạt, mua lại và ngừng mua của từng vùng; tỷ lệ giữ chân sau 3/6 tháng? | S18 | READY |
| M24 | Vùng nào mở nhiều khách mới nhưng doanh thu/khách và tỷ lệ mua lại thấp? | S19 | DERIVED |
| M25 | Khách nào có tiềm năng bán chéo nhóm sản phẩm do đang mua ít SKU hơn nhóm khách tương đồng? | S41 | DERIVED |
| M26 | Khách hàng nào có share-of-wallet nội bộ thấp: doanh thu lớn nhưng chỉ mua một nhóm sản phẩm? | S23 | DERIVED |
| M27 | Tỉnh/huyện nào có ít khách hoạt động, ít đơn hoặc doanh thu/khách thấp hơn chuẩn miền? | S14 | READY |
| M28 | Tỷ lệ khách không gán TDV, sai vùng hoặc thiếu thông tin DMS theo tháng là bao nhiêu? | S38 | READY |
| M29 | NPP/chi nhánh nào có tăng trưởng khách hàng tốt nhưng công nợ hoặc tồn kho xấu đi? | S15 | READY |
| M30 | Danh sách 20 khách hàng ưu tiên cần giữ, thu hồi, tái kích hoạt hoặc mở rộng trong tháng tới là ai? | S48 | DERIVED |
| M31 | Nhóm sản phẩm/SKU nào đóng góp nhiều nhất vào tăng/giảm của miền/kênh theo tháng? | S21 | READY |
| M32 | SKU chiến lược đạt bao nhiêu % target tại từng vùng; vùng nào có khoảng trống độ phủ lớn nhất? | S46 | PARTIAL |
| M33 | SKU nào doanh thu giảm do ít khách mua, ít đơn, giảm lượng/đơn hay giảm giá bán? | S21 | READY |
| M34 | Sản phẩm mới đạt độ phủ và doanh thu sau 1/3/6 tháng thế nào tại từng vùng? | S22 | DERIVED |
| M35 | Chương trình khuyến mãi nào có nhiều khách tham gia nhưng không tạo tăng trưởng; chương trình nào tạo uplift tốt? | S12 | PARTIAL |
| M36 | Tỷ lệ trả hàng, chiết khấu và hàng tặng trên doanh thu của từng vùng thay đổi ra sao? | S09 | READY |
| M37 | Tổng nợ, nợ quá hạn, DSO và thu tiền của từng vùng/QLV qua từng tháng; đơn vị nào xấu đi nhanh nhất? | S25 | BLOCKED_HISTORY |
| M38 | Khách nào cần dừng/bóp bán vì nợ xấu; doanh thu có nguy cơ ảnh hưởng là bao nhiêu? | S26 | PARTIAL |
| M39 | SKU nào thiếu hàng ở miền/kênh và làm mất doanh số; SKU nào tồn cao hơn nhu cầu 3–6 tháng? | S47 | DERIVED |
| M40 | Hàng cận date/chậm luân chuyển nào cần chuyển vùng, đẩy bán hoặc dừng nhập? | S28 | PARTIAL |
| M41 | Với ETC, kế hoạch thầu, tỷ lệ trúng, doanh thu thực hiện và thu tiền từng tháng của từng vùng/khách hàng thế nào? | S29 | PARTIAL |
| M42 | Hợp đồng/gói thầu nào có tỷ lệ thực hiện thấp, còn giá trị lớn hoặc sắp hết hiệu lực? | S29 | PARTIAL |
| M43 | Dự báo cuối tháng của từng vùng/QLV là bao nhiêu; vùng nào có xác suất không đạt cao nhất? | S35 | PARTIAL |
| M44 | Với từng vùng dưới kế hoạch: ba nguyên nhân định lượng, ba hành động, người chịu trách nhiệm và deadline là gì? | S36 | BLOCKED |
| V01 | Đội tôi đạt bao nhiêu doanh số và bao nhiêu % target tháng; MoM, YoY và YTD thế nào? | S43 | PARTIAL |
| V02 | Còn thiếu bao nhiêu để đạt 65/70%, 80%, 100% và 120%; mỗi ngày còn lại cần bán bao nhiêu? | S43 | PARTIAL |
| V03 | Doanh số từng ngày/tuần đang cao hay thấp hơn nhịp cần thiết; ngày nào không có phát sinh? | S03 | DERIVED |
| V04 | Nhân viên nào đóng góp nhiều nhất vào tăng/giảm doanh số đội tháng này? | S39 | READY |
| V05 | Nếu loại đơn hàng lớn bất thường và hàng trả, kết quả thực chất của đội là bao nhiêu? | S09 | READY |
| V06 | Doanh thu đội đến từ bao nhiêu khách, bao nhiêu đơn; AOV và tần suất mua thay đổi thế nào? | S07 | READY |
| V07 | So với 3 tháng gần nhất, tháng này đội giảm ở số khách, số đơn, sản lượng hay giá trị đơn? | S05 | DERIVED |
| V08 | Tỉnh/địa bàn con nào đang dưới kế hoạch; phần hụt là bao nhiêu và TDV nào phụ trách? | S43 | PARTIAL |
| V09 | Dự báo cuối tháng của đội theo run-rate hiện tại; kịch bản cơ sở/tốt/xấu là bao nhiêu? | S35 | PARTIAL |
| V10 | Hôm nay/tuần này cần ưu tiên khách hàng, sản phẩm và nhân viên nào để đóng gap lớn nhất? | S48 | DERIVED |
| V11 | Doanh số, target và % hoàn thành từng TDV theo tháng; xếp hạng và xu hướng 3/6 tháng? | S39 | READY |
| V12 | Ai dưới 65/70%, dưới 80%, đạt 100% hoặc vượt 120%; mỗi người còn thiếu bao nhiêu tiền? | S31 | READY |
| V13 | Ai giảm liên tiếp 2–3 tháng; nguyên nhân nằm ở khách mất, ít đơn, ít SKU hay giá trị đơn giảm? | S39 | READY |
| V14 | Ai có nhiều khách phụ trách nhưng tỷ lệ khách mua thấp; ai có ít khách nhưng doanh thu/khách cao? | S44 | READY |
| V15 | Ai mở nhiều khách mới nhưng tỷ lệ mua lại thấp; ai tái kích hoạt khách tốt nhất? | S44 | READY |
| V16 | Ai có ngày làm việc/đi tuyến nhưng không phát sinh đơn; tỷ lệ viếng thăm có đơn là bao nhiêu? | S34 | READY |
| V17 | Nhân viên nào có doanh số nhưng thiếu target, thiếu manager, sai địa bàn hoặc trùng mã? | S38 | READY |
| V18 | Thưởng và phụ cấp từng người thay đổi thế nào; có điểm nào không khớp KPI/chính sách? | S33 | PARTIAL |
| V19 | Top khách hàng đội tôi từng tháng là ai; khách nào tăng/giảm mạnh nhất? | S20 | READY |
| V20 | Khách đã mua tháng trước nhưng chưa mua tháng này là ai; doanh thu có nguy cơ mất bao nhiêu? | S40 | READY |
| V21 | Khách im lặng 30/60/90 ngày là ai; lần mua gần nhất, giá trị và sản phẩm thường mua là gì? | S40 | READY |
| V22 | Khách mới tháng này là ai; đã có đơn lặp lại chưa và TDV nào phụ trách? | S18 | READY |
| V23 | Khách mua lại/tái kích hoạt là ai; doanh thu phục hồi so trước khi ngừng mua thế nào? | S18 | READY |
| V24 | Khách nào giảm tần suất mua, AOV hoặc số SKU/đơn so với 3 tháng trước? | S44 | READY |
| V25 | Khách nào chỉ mua một nhóm sản phẩm và có cơ hội bán chéo rõ nhất? | S41 | DERIVED |
| V26 | Khách nào mua ít hơn các khách tương đồng cùng tỉnh/phân khúc? | S44 | READY |
| V27 | Khách nào chưa gán TDV, sai mã, sai tỉnh/vùng hoặc không có tên trong DMS? | S38 | READY |
| V28 | Danh sách khách ưu tiên tuần này theo bốn mục tiêu: giữ khách lớn, tái kích hoạt, thu nợ và bán chéo? | S48 | DERIVED |
| V29 | Top/bottom sản phẩm từng tháng của đội; SKU nào làm tăng/giảm doanh số nhiều nhất? | S21 | READY |
| V30 | SKU trọng tâm đạt bao nhiêu % target theo từng TDV và khách hàng; khoảng thiếu bao nhiêu? | S46 | PARTIAL |
| V31 | Sản phẩm nào nhiều khách mua nhưng lượng/đơn thấp; sản phẩm nào ít khách nhưng AOV cao? | S23 | DERIVED |
| V32 | Cặp sản phẩm nào thường mua cùng; khách nào phù hợp bán combo nhưng chưa mua? | S41 | DERIVED |
| V33 | Đơn nào bị hủy, trả, điều chỉnh, giao/hóa đơn chậm hoặc chưa tìm thấy hóa đơn? | S42 | READY |
| V34 | Chương trình khuyến mãi nào đội đang dùng; khách tham gia, số đơn và doanh thu trước–trong–sau chương trình thế nào? | S12 | PARTIAL |
| V35 | Tổng nợ và nợ quá hạn của đội theo tháng; khách nào mới chuyển sang nhóm tuổi nợ xấu hơn? | S25 | BLOCKED_HISTORY |
| V36 | Khách nào vừa nợ quá hạn vừa giảm mua; TDV phụ trách và số tiền cần thu là bao nhiêu? | S26 | PARTIAL |
| V37 | Thu tiền tháng này của từng TDV/khách so kế hoạch; cam kết thu nào đã quá hạn? | S45 | BLOCKED_HISTORY |
| V38 | SKU khách đang cần nhưng kho thiếu là gì; đơn/doanh thu nào có nguy cơ mất vì thiếu hàng? | S47 | DERIVED |
| V39 | SKU tồn cao/chậm bán/cận date trong phạm vi vùng là gì; khách nào phù hợp để xử lý tồn? | S28 | PARTIAL |
| V40 | Cuối tháng, những ngoại lệ nào chưa xử lý: target thiếu, khách chưa gán, đơn chưa hóa đơn, nợ xấu, hàng trả và dữ liệu chưa đồng bộ? | S38 | READY |

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
