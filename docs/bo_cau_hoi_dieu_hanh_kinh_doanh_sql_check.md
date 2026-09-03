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

### S10 — Kiểm tra nguồn giá vốn, lợi nhuận — BLOCKED

Chỉ còn chặn phần **lợi nhuận** (C14, C15, C19). Phần chiết khấu/doanh thu gộp/doanh thu thuần đã
tách sang `S87` — xem lý do ở đó, cột `DiscountRate` có thật, không cần chờ DNH cho phần này nữa.

Kiểm cột lần đầu (03/09/2026) tìm thấy `OriginalUnitCost`/`UnitCost` (numeric) trên `BRV_TheKho`,
`BRVSX_TheKho`, `BRVSX_TonKhoDK` — nhưng đó là **giá vốn tồn kho** (snapshot định giá kho, cùng nguồn
đã dùng cho A3 — giá trị tồn kho), không phải giá vốn hàng bán tại thời điểm xuất hóa đơn. Không có
cột giá vốn nào trên `vHoaDonTotal`/`vHoaDonETCTotal`. Dùng giá vốn tồn kho làm giá vốn hàng bán có
nguy cơ sai lệch nếu giá nhập biến động theo thời gian (thiên lệch biên lợi nhuận theo xu hướng giá,
không phải theo hiệu quả bán hàng thật) — đây là quyết định nghiệp vụ, không tự chọn thay DNH.

    SELECT o.name ObjectName,c.name ColumnName,t.name DataType
    FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
    JOIN sys.types t ON t.user_type_id=c.user_type_id
    WHERE o.schema_id=SCHEMA_ID('dbo')
      AND (c.name LIKE '%Cost%' OR c.name LIKE '%GiaVon%' OR c.name LIKE '%Profit%'
        OR c.name LIKE '%LoiNhuan%')
    ORDER BY o.name,c.column_id;

### S87 — Doanh thu gộp, chiết khấu, hàng trả và doanh thu thuần — PARTIAL

Cho câu hỏi "doanh thu gộp, chiết khấu, khuyến mãi, hàng trả và doanh thu thuần từng tháng". Xác nhận
thật trên Bravo 03/09/2026: `Amount9 = UnitPrice × Quantity` (giá GỘP, chưa trừ chiết khấu) — mẫu
`UnitPrice=54.285,71 × Quantity=60 = 3.257.142,86 ≈ Amount9=3.257.143`; thử `Amount9/(1-DiscountRate)`
KHÔNG khớp, nên `Amount9` không phải giá đã trừ chiết khấu. Công thức đúng:

- Doanh thu gộp = `Amount9` (dòng có `UnitPrice>0`, theo nguyên tắc pass/fail số 5)
- Chiết khấu = `Amount9 × DiscountRate`
- Hàng trả/điều chỉnh = `Amount9<0 OR DocCode='HC'` (nhất quán với S09)
- Doanh thu thuần = tổng `Amount9` mọi dòng (đã tự trừ hàng trả) trừ tổng chiết khấu

**PARTIAL — phần khuyến mãi**: catalog có hệ khuyến mãi thật (`DMS_CTKM`, `DMS_CTKMOnTop1/2/3`,
`DMS_DonHangCTKM`, cột `KMAmount` trên bảng đơn hàng BRV) nhưng **chưa nối vào** — `S12` đã cảnh báo
một đơn có thể thuộc nhiều chương trình CTKM cùng lúc, cộng ngang theo dòng hóa đơn sẽ đúp. Cần dựng
riêng và đối chiếu tổng trước khi coi khuyến mãi là số đáng tin.

    SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,Channel,
           SUM(CASE WHEN Amount9>0 THEN Amount9 ELSE 0 END) DoanhThuGop,
           SUM(CASE WHEN Amount9>0 THEN Amount9*ISNULL(DiscountRate,0) ELSE 0 END) ChietKhau,
           SUM(CASE WHEN Amount9<0 OR DocCode='HC' THEN Amount9 ELSE 0 END) HangTraDieuChinh,
           SUM(Amount9)
             - SUM(CASE WHEN Amount9>0 THEN Amount9*ISNULL(DiscountRate,0) ELSE 0 END) DoanhThuThuan
    FROM #sales
    GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1),Channel
    ORDER BY MonthStart,Channel;

### S11 — Xu hướng giá bán thực tế theo SKU và SKU nào xói mòn giá — READY

Xác nhận thật trên Bravo 03/09/2026: công thức `RealizedPrice = SUM(Amount9)/SUM(Quantity đã bán,
UnitPrice>0)` khớp tuyệt đối với chatbot đã trả cho SKU 81350000001 kênh ETC (T6: 10.026,79≈10.027;
T7: 10.000,00; T8: 9.465,20≈9.465) — công thức đúng, không cần sửa.

    SELECT DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,Channel,ItemCode,
           SUM(Amount9) Revenue,SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END) PaidQty,
           SUM(Amount9)/NULLIF(SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END),0) RealizedPrice
    FROM #sales WHERE UnitPrice>0
    GROUP BY DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1),Channel,ItemCode
    ORDER BY ItemCode,MonthStart;

Câu C16 còn hỏi "SKU nào xói mòn giá" — bảng trên là nguyên liệu thô, không trả lời trực tiếp. SQL
dưới đây trả THẲNG danh sách SKU có giá giảm trong cửa sổ 3 tháng gần nhất, phân biệt xói mòn LIÊN
TỤC (mọi tháng đều giảm) và KHÔNG LIÊN TỤC (giảm ròng nhưng có tháng hồi phục xen giữa — dạng chữ V) —
cùng cách phân loại chatbot đã dùng khi trả lời trực tiếp người dùng.

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

### S12 — Hiệu quả khuyến mãi gắn đơn — PARTIAL

`AssociatedRevenue` không được cộng ngang vì một đơn có thể thuộc nhiều CTKM cùng lúc.

**Phải tách bạch bốn con số, không được rút gọn thành "số đơn" và "số khách".** `LEFT JOIN` sang hóa
đơn nghĩa là có đơn gắn CTKM nhưng chưa/không xuất hóa đơn — trong khi `AssociatedRevenue` chỉ cộng
phần đã xuất. Lấy `Revenue / Orders` sai mẫu số; phải dùng `Orders_DaXuatHD`.

UAT trực tiếp 03/09/2026 bắt được lỗi thật nhờ chỗ này: với `Q1.2026_BPNGAM_10_TQ` tháng 01/2026,
số thật là **382 đơn / 313 đơn đã xuất HĐ / 333 khách / 309 khách đã xuất HĐ**, doanh thu
2.964.639.197 → bình quân/đơn đã xuất HĐ = **9,47 triệu**. Chatbot trả "Số đơn (đã xuất hóa đơn) =
309" và "DT bình quân/đơn = 9,6 triệu" — tức lấy **số KHÁCH đã xuất HĐ** rồi gọi là **số ĐƠN**, và
chia doanh thu cho mẫu số sai. Bản thân tool `promotion_effectiveness` trả đúng 313; sai lệch phát
sinh ở khâu trình bày, không phải ở tool.

Lưu ý khi đối chiếu: **không dùng quy tắc "đơn phải ≥ khách" để bắt lỗi.** `Orders_DaXuatHD` đếm trên
tập đơn đã xuất hóa đơn, còn `Customers` đếm trên TOÀN BỘ đơn gắn CTKM, nên 313 < 333 là hoàn toàn
hợp lệ. Chỉ được kết luận bằng cách so trực tiếp từng con số với checker này.

**Tên chương trình bị trùng giữa các kỳ** (`T9.2025_BPNGAM_10_TQ`, `Q4.2025_BPNGAM_10_TQ`,
`Q1.2026_BPNGAM_10_TQ` đều tên "Bổ phế Ngậm mua 10 tặng 01"). Luôn hiển thị kèm `Code` và `MonthEnd`;
gộp theo `Name` là trộn lẫn các đợt khác nhau.

    WITH po AS (
      SELECT x.ProgId,x.OrderId,MAX(h.CustomerCode) CustomerCode,MAX(h.DocDate) DocDate
      FROM dbo.DMS_DonHangCTKM x JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
      WHERE h.DocDate>=@FromDate AND h.DocDate<@ToDate GROUP BY x.ProgId,x.OrderId
    ), inv AS (
      SELECT TRY_CONVERT(int,DMSId) OrderId,SUM(Amount9) Revenue
      FROM #sales WHERE TRY_CONVERT(int,DMSId) IS NOT NULL GROUP BY TRY_CONVERT(int,DMSId)
    )
    SELECT EOMONTH(po.DocDate) MonthEnd,p.Code,p.Name,
           COUNT(*) Orders,
           COUNT(inv.OrderId) Orders_DaXuatHD,
           COUNT(DISTINCT po.CustomerCode) Customers,
           COUNT(DISTINCT CASE WHEN inv.OrderId IS NOT NULL
                               THEN po.CustomerCode END) Customers_DaXuatHD,
           SUM(ISNULL(inv.Revenue,0)) AssociatedRevenue,
           SUM(ISNULL(inv.Revenue,0))/NULLIF(COUNT(inv.OrderId),0) RevenuePerOrder
    FROM po JOIN dbo.DMS_CTKM p ON p.Id=po.ProgId LEFT JOIN inv ON inv.OrderId=po.OrderId
    GROUP BY EOMONTH(po.DocDate),p.Code,p.Name
    ORDER BY AssociatedRevenue DESC;

### S13 — Like-for-like tách khỏi tăng trưởng do mở mới — DERIVED

Chỉ số LFL theo năm, trên tập khách có doanh thu ở CẢ hai kỳ:

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

Câu C20 hỏi **tách** tăng trưởng LFL khỏi tăng trưởng do mở mới — một con số % ở trên không trả lời
được. SQL dưới đây phân rã biến động thành các cấu phần cộng lại đúng bằng tổng, kèm số khách mỗi
nhóm. Cửa sổ là 3 tháng gần nhất so 3 tháng liền trước (với `@MonthStart='2026-08-01'` là T6–T8 so
T3–T5), trùng cách chatbot đang trình bày để đối chiếu được trực tiếp.

Định nghĩa LFL ở đây **rộng hơn** truy vấn trên: gồm mọi khách có doanh thu kỳ trước, kể cả khách đã
về 0 ở kỳ này — nên phần rời bỏ nằm TRONG cấu phần LFL và được tách ra làm dòng con để nhìn rõ. Nhờ
vậy `LFL + Mở mới = Tăng trưởng tổng` khít tuyệt đối, không có phần dư (dòng kiểm tra luôn = 0).

**Chưa khớp với chatbot ở cấu phần LFL — cần đối chiếu định nghĩa trước khi kết luận ai đúng.** Bản
chạy 03/09/2026 (T6–T8 so T3–T5): ba con số tổng khớp tuyệt đối (217,56 / 226,84 / -9,28 tỷ), số
khách mỗi nhóm lệch không đáng kể (12.020 vs 12.014; 3.049 vs 3.046; 2.996 vs 2.995), nhưng LFL của
chatbot là **-37,40 tỷ** kèm một khoản **"phần dư chưa phân loại" +2,87 tỷ**, còn ở đây LFL là
**-34,49 tỷ** và không có phần dư. Đã loại hai giả thuyết: giao dịch thiếu mã khách = **0 dòng**;
hàng trả/điều chỉnh cả kỳ chỉ **-502 triệu**, không đủ giải thích 2,87 tỷ. Nguồn gốc khoản dư đó
chưa tái tạo được từ dữ liệu thô — phải xem `audit_log` của phiên hỏi C20 để biết chatbot phân loại
theo tiêu chí nào. **Không dùng chênh lệch này làm căn cứ kết luận chatbot sai khi chưa làm rõ.**

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

### S15 — Năng suất chi nhánh nội bộ (KHÔNG phải NPP) — PARTIAL

**Không có chiều nhà phân phối trong dữ liệu.** Kiểm thật 03/09/2026 trên cả hai view hóa đơn, kỳ
12 tháng: `DistributorCode` chỉ có **3 giá trị** trong toàn bộ dữ liệu (`OTC1`, `OTC`, `ETC`) — đó là
nhãn kênh, không phải danh tính NPP. `BranchCode` chỉ có **4 giá trị** (`A01`, `B02`, `B03`, `B04`) —
là chi nhánh kho **nội bộ của DNH**, không phải kho của NPP bên ngoài. Không dòng nào trống.

Vì vậy checker này **chỉ trả lời được phần "chi nhánh nội bộ"**, KHÔNG trả lời được:
- "NPP nào doanh thu giảm" — không có danh tính NPP để tách;
- "NPP nào tồn kho tăng" — tồn kho theo kho nội bộ, không theo NPP;
- "NPP nào nợ xấu" — công nợ tra theo khách hàng hoặc vùng/kênh, không có trường NPP.

**Chatbot từ chối C25/M29 với đúng lý do này là HÀNH VI ĐÚNG, phải chấm ĐẠT** theo quy tắc ở
`huong_dan_ban_giao_uat.md` (câu thiếu nguồn tính đạt khi nói rõ giới hạn, không suy đoán). Trước
03/09/2026 checker này gắn nhãn READY — nếu tester đối chiếu bảng dưới, sẽ chấm SAI cho một câu trả
lời đúng.

Cột này cũng **chưa được đồng bộ xuống kho local** (`vhoadon_otc`/`vhoadon_etc` trong `warehouse.db`
không có `branch_code`/`distributor_code`), nên chatbot không nhìn thấy kể cả phần chi nhánh nội bộ.

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

Truy vấn trên phục vụ **C28** (loại ảnh hưởng của chuyển khách/chuyển nhân viên). Nó KHÔNG trả lời
**C27** — câu này hỏi có dịch chuyển doanh thu bất thường giữa kênh/miền/chi nhánh/nhân viên qua các
tháng hay không. SQL dưới đây trả thẳng danh sách biến động bất thường trên cả bốn chiều, xếp theo
mức tiền, để không phải tự dò bảng MoM.

Ngưỡng đề xuất: biến động ≥ 25% **và** ≥ 1 tỷ đồng — hai điều kiện cùng lúc để loại vừa nhiễu phần
trăm của đơn vị nhỏ, vừa dao động nhỏ của đơn vị lớn. **Ngưỡng này do MCNA đặt, cần DNH chốt.**

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

Cho **C28** ("loại ảnh hưởng đổi địa bàn/chuyển NV/chuyển khách thì tăng trưởng thực còn bao nhiêu").
Cách làm phòng thủ được: **không** cố nặn ra một con số đã "loại sạch mọi ảnh hưởng" — mà đo tăng
trưởng trên **nhóm khách hoàn toàn không bị xáo trộn** (cùng một mã nhân viên và cùng một vùng ở cả
hai kỳ), rồi tách riêng phần bị loại kèm quy mô tiền để người đọc biết đã bỏ ra bao nhiêu.

**Giới hạn phải nói rõ khi trình bày:** catalog không có bảng lịch sử phân công, nên cách này KHÔNG
xử lý được trường hợp nhân viên/QLV nghỉ mà chưa có người kế nhiệm — khách của họ sẽ rơi vào nhóm
"bị xáo trộn" hoặc nhóm rời bỏ chứ không quy được về đơn vị cũ. Chatbot từ chối đưa một con số duy
nhất cho C28 là **hành vi đúng**; bảng dưới là mức chi tiết cao nhất mà dữ liệu hiện có cho phép.

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

### S18 — Khách mới, mua lại, hoạt động — READY

> ⚠️ **KHÔNG được cộng các dòng của truy vấn thứ nhất để ra tổng công ty.** Mỗi dòng là
> `COUNT(DISTINCT CustomerCode)` trong phạm vi (tháng × vùng × QLV); một khách xuất hiện ở nhiều
> nhóm sẽ bị đếm nhiều lần. Muốn tổng thì dùng truy vấn thứ hai.
>
> Đo thật 03/09/2026, T8/2026: khách mới **distinct toàn công ty = 627**, nhưng nếu cộng các nhóm sẽ
> ra số lớn hơn nhiều — riêng nhóm `ManagerCode IS NULL` đã là 587 khách, mà 572 trong số đó ĐỒNG
> THỜI có dòng gắn QLV. Cộng ngang là đếm trùng gần như toàn bộ.

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

Tổng đúng theo tháng cho **C29** — đếm distinct một lần trên toàn công ty, kèm cột chẩn đoán cho biết
bao nhiêu khách chỉ có dòng `ManagerCode` rỗng (nhóm dễ bị bỏ sót khi trình bày theo QLV):

    WITH snaps AS (
      SELECT EOMONTH(SaveDate) MonthEnd,MAX(SaveDate) SaveDate
      FROM dbo.FACT_TongHopKhachHang
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate GROUP BY EOMONTH(SaveDate)
    ), f AS (
      SELECT EOMONTH(f.SaveDate) MonthEnd,f.ManagerCode,f.CustomerCode,f.IsNC,f.IsRO,f.IsAC
      FROM dbo.FACT_TongHopKhachHang f JOIN snaps s ON s.SaveDate=f.SaveDate
      WHERE (@AreaCode IS NULL OR f.AreaCode=@AreaCode)
    )
    SELECT MonthEnd,
      COUNT(DISTINCT CustomerCode) TongKhach,
      COUNT(DISTINCT CASE WHEN IsNC=1 THEN CustomerCode END) KhachMoi,
      COUNT(DISTINCT CASE WHEN IsRO=1 THEN CustomerCode END) KhachMuaLai,
      COUNT(DISTINCT CASE WHEN IsAC=1 THEN CustomerCode END) KhachAC,
      COUNT(DISTINCT CASE WHEN IsNC=1 AND ManagerCode IS NOT NULL
                          THEN CustomerCode END) KhachMoi_CoQLV,
      COUNT(DISTINCT CASE WHEN IsNC=1 THEN CustomerCode END)
        - COUNT(DISTINCT CASE WHEN IsNC=1 AND ManagerCode IS NOT NULL
                              THEN CustomerCode END) KhachMoi_BoSotNeuLocQLV
    FROM f GROUP BY MonthEnd ORDER BY MonthEnd;

Cột cuối là mức chênh nếu chỉ lấy khách có QLV: T8/2026 là **627 − 612 = 15 khách (2,4%)**. Bản chạy
UAT 03/09 cho thấy chatbot báo đúng **612** — tức đang lọc bỏ khách chưa gắn QLV. Chênh nhỏ nhưng
phải nói rõ, vì đây là chỉ số đếm khách, không phải ước lượng.

Cờ `IsAC` chỉ dành cho CS (Chợ sỉ) và TK (kênh MT) theo DNH chốt 27/08/2026 — `KhachAC` KHÔNG phải
"khách hoạt động" của toàn công ty, không được dùng thay cho `TongKhach`.

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

Truy vấn trên là đường cong thô, chưa trả lời C30 — câu này hỏi **tỷ lệ** giữ chân tại đúng mốc
1/3/6/12 tháng, **tách theo kênh và miền**. SQL dưới đây trả thẳng bảng đó.

**Cohort đầu cửa sổ bị kiểm duyệt trái, phải loại khi đọc kết quả.** `MIN(DocDate)` chỉ nhìn được
trong phạm vi `#sales`, nên mọi khách đã mua từ trước `@FromDate` đều bị dồn vào tháng đầu tiên và
trông như "khách mới". Bản chạy tay của người dùng cho cohort đầu tiên **7.820 khách** ở tuổi 0,
trong khi các cohort thật chỉ vài trăm — chênh hơn 20 lần. Cột `GhiChu` đánh dấu dòng này.

Cohort chưa đủ tuổi trả `NULL` chứ **không trả 0** — 0 sẽ bị đọc nhầm thành "mất sạch khách".

**Chênh định nghĩa với chatbot — chờ DNH chốt A10, không chấm sai bên nào.** Checker này lấy cohort =
tháng có hóa đơn đầu tiên quan sát được (proxy, đúng như nhãn DERIVED). Chatbot dùng cờ `IsNC` —
định nghĩa "khách mở mới" chính thức của DNH. Hai cách cho quy mô cohort rất khác nhau: T10/2025 kênh
OTC ra **2.433 khách** theo cách này, còn chatbot báo **341**. Chừng nào A10 chưa chốt thì **tỷ lệ giữ
chân của hai bên không so trực tiếp được** — phải thống nhất nguồn cohort trước. Nếu DNH chốt dùng
`IsNC`, thay CTE `f` bằng truy vấn lấy tháng đầu tiên có `IsNC=1` trong `FACT_TongHopKhachHang`.

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

Truy vấn trên phục vụ **M21/V19** (top khách, ai tăng/giảm mạnh). Nó **không** trả lời **C31** — câu
này hỏi tổng doanh thu MẤT từ khách ngừng mua so với doanh thu TĂNG THÊM từ khách mới/tái kích hoạt,
theo từng tháng. Bảng trên vừa chỉ có một cặp tháng, vừa cắt `TOP (100)` nên cộng lại không ra tổng.

Lưới khách × tháng ở dưới là bắt buộc: khách vắng mặt một tháng thì không có dòng trong `#sales`, nếu
dùng `LAG` trực tiếp sẽ so nhầm với tháng gần nhất CÓ giao dịch chứ không phải tháng liền trước — đúng
nhóm khách ngừng mua lại bị bỏ sót.

**Cả checker lẫn chatbot đều đang dùng định nghĩa tạm — chờ DNH chốt câu B3 (ngưỡng khách ngừng
mua).** Đối chiếu T6/2026:

| | Chatbot | Checker |
|---|---:|---:|
| Doanh thu mất | -10,27 tỷ | -14,71 tỷ |
| Doanh thu thêm | +3,30 tỷ | +15,27 tỷ |
| Tỷ lệ bù đắp | 32% | 104% |

- **Chatbot lệch bất đối xứng**: tự ghi là chỉ lấy "khách mới xuất hiện **lần đầu**" và cắt tối đa
  200 khách/nhóm/tháng. C31 hỏi "khách mới **/tái kích hoạt**" — loại nhóm tái kích hoạt khỏi vế tăng
  thêm trong khi vế mất vẫn tính đủ sẽ kéo tỷ lệ bù đắp xuống thấp giả tạo. Kết luận "chỉ bù được 1/3"
  từ đó **không dùng được**.
- **Checker trước đây cũng lệch**: coi vắng mặt ĐÚNG MỘT THÁNG đã là "ngừng mua", nên khách mua cách
  tháng nhảy qua lại giữa hai nhóm và thổi phồng cả hai vế.

Vì B3 chưa chốt, SQL dưới đây **tính sẵn ba ngưỡng cạnh nhau** (`_N1`, `_N2`, `_N3` = im lặng 1, 2
hoặc 3 tháng liên tiếp) thay vì tự chọn một con số. Định nghĩa đối xứng ở cả hai vế: "ngừng mua" là
im lặng đủ N tháng sau khi có doanh thu, "mới/tái kích hoạt" là có doanh thu sau khi im lặng đủ N
tháng. Cả ba ngưỡng tính trên cùng một tập tháng (`P3 IS NOT NULL`) để so được với nhau.

**Đây là bảng để DNH chốt B3**: nhìn ba cột `TyLeBuDap_N1/N2/N3` sẽ thấy kết luận "mất khách có được
bù không" nhạy đến mức nào với ngưỡng. Giữa năm ngưỡng đổi là kết luận đổi hẳn (T3/2026: 118,9% ở N1
nhưng 40,6% ở N2). Chốt xong thì bỏ hai ngưỡng còn lại và sửa chatbot về cùng ngưỡng đó.

**Nhưng sai lệch của chatbot KHÔNG phải do khác ngưỡng** — bản chạy 03/09 cho thấy nó nằm thấp hơn
toàn bộ dải ba ngưỡng ở cả ba tháng:

| Tháng | Chatbot | N1 | N2 | N3 |
|---|---:|---:|---:|---:|
| T6/2026 | 32% | 103,8% | 82,9% | 69,0% |
| T7/2026 | 37% | 127,6% | 112,9% | 91,8% |
| T8/2026 | 40% | 116,4% | 119,7% | 137,2% |

Chọn ngưỡng nào cũng không ra 32–40%. Nguyên nhân là việc loại nhóm tái kích hoạt khỏi vế tăng thêm
(bất đối xứng), không phải bất đồng định nghĩa churn. **Đây là lỗi phải sửa, không phải điểm chờ
DNH.**

    WITH cm AS (
      SELECT CustomerCode,DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1) MonthStart,
             SUM(Amount9) Rev
      FROM #sales GROUP BY CustomerCode,DATEFROMPARTS(YEAR(DocDate),MONTH(DocDate),1)
    ), months AS (SELECT DISTINCT MonthStart FROM cm
    ), grid AS (
      SELECT c.CustomerCode,m.MonthStart,ISNULL(x.Rev,0) Rev
      FROM (SELECT DISTINCT CustomerCode FROM cm) c
      CROSS JOIN months m
      LEFT JOIN cm x ON x.CustomerCode=c.CustomerCode AND x.MonthStart=m.MonthStart
    ), mv AS (
      SELECT CustomerCode,MonthStart,Rev,
             LAG(Rev,1) OVER(PARTITION BY CustomerCode ORDER BY MonthStart) P1,
             LAG(Rev,2) OVER(PARTITION BY CustomerCode ORDER BY MonthStart) P2,
             LAG(Rev,3) OVER(PARTITION BY CustomerCode ORDER BY MonthStart) P3
      FROM grid
    )
    SELECT MonthStart,
      SUM(CASE WHEN Rev=0 AND P1>0 THEN P1 ELSE 0 END) Mat_N1,
      SUM(CASE WHEN Rev>0 AND P1=0 THEN Rev ELSE 0 END) Them_N1,
      100.0*SUM(CASE WHEN Rev>0 AND P1=0 THEN Rev ELSE 0 END)
        /NULLIF(SUM(CASE WHEN Rev=0 AND P1>0 THEN P1 ELSE 0 END),0) TyLeBuDap_N1,
      SUM(CASE WHEN Rev=0 AND P1=0 AND P2>0 THEN P2 ELSE 0 END) Mat_N2,
      SUM(CASE WHEN Rev>0 AND P1=0 AND P2=0 THEN Rev ELSE 0 END) Them_N2,
      100.0*SUM(CASE WHEN Rev>0 AND P1=0 AND P2=0 THEN Rev ELSE 0 END)
        /NULLIF(SUM(CASE WHEN Rev=0 AND P1=0 AND P2>0 THEN P2 ELSE 0 END),0) TyLeBuDap_N2,
      SUM(CASE WHEN Rev=0 AND P1=0 AND P2=0 AND P3>0 THEN P3 ELSE 0 END) Mat_N3,
      SUM(CASE WHEN Rev>0 AND P1=0 AND P2=0 AND P3=0 THEN Rev ELSE 0 END) Them_N3,
      100.0*SUM(CASE WHEN Rev>0 AND P1=0 AND P2=0 AND P3=0 THEN Rev ELSE 0 END)
        /NULLIF(SUM(CASE WHEN Rev=0 AND P1=0 AND P2=0 AND P3>0 THEN P3 ELSE 0 END),0) TyLeBuDap_N3
    FROM mv
    WHERE P3 IS NOT NULL
    GROUP BY MonthStart ORDER BY MonthStart;

### S21 — Đóng góp tăng/giảm theo SKU (cột nhóm KHÔNG tin được) — PARTIAL

**Phần SKU dùng được; phần "nhóm sản phẩm" thì KHÔNG.** Kiểm thật 03/09/2026, kỳ 12 tháng:
`GroupCode` trên hai view hóa đơn là **hai hệ mã khác nhau, và bên OTC không phải nhóm sản phẩm**:

| Kênh | Giá trị | Thực chất |
|---|---|---|
| OTC | `DM1`, `DM2`, `DM3` — chỉ 3 giá trị, 55 SKU | **Bậc thưởng nhóm hàng** trong chính sách lương (xem `DIM_BacThuong`), không phải phân loại sản phẩm |
| ETC | `0`,`1`,`2`,`3`,`4` — 257 SKU | Mã số khác hệ, không cùng nghĩa với OTC |

Gộp theo `GroupCode` rồi gọi là "nhóm sản phẩm" sẽ cho ra bảng trông hợp lý nhưng **trộn bậc thưởng
với mã số vô nghĩa** — đúng loại bẫy như `S15` (NPP). Hai view còn khác cả kiểu dữ liệu (`int` vs
`varchar`), nên `#sales` phải `CONVERT(varchar(50), GroupCode)` mới union được.

Vì vậy với C33/M31/V29, **chỉ dùng cột `ItemCode`**; muốn trả lời theo nhóm sản phẩm thật thì phải
được DNH cấp danh mục ngành hàng và khoá nối vào mặt hàng. Chatbot từ chối phần "nhóm sản phẩm" hoặc
chỉ trả lời theo SKU là **hành vi đúng**.

    WITH p AS (
      SELECT GroupCode,ItemCode,
        SUM(CASE WHEN DocDate>=@MonthStart AND DocDate<@MonthEnd THEN Amount9 ELSE 0 END) Cur,
        SUM(CASE WHEN DocDate>=DATEADD(month,-1,@MonthStart) AND DocDate<@MonthStart THEN Amount9 ELSE 0 END) Prev
      FROM #sales GROUP BY GroupCode,ItemCode
    )
    SELECT GroupCode,ItemCode,Cur,Prev,Cur-Prev Delta,
           100.0*(Cur-Prev)/NULLIF(SUM(Cur-Prev) OVER(),0) ContributionPct
    FROM p ORDER BY Delta DESC;

### S22 — Sản phẩm mới: doanh thu và độ phủ theo tuổi — DERIVED

    WITH f AS (
      SELECT ItemCode,MIN(DocDate) FirstSaleDate FROM #sales GROUP BY ItemCode
    )
    SELECT EOMONTH(f.FirstSaleDate) LaunchMonth,s.ItemCode,
           COUNT(DISTINCT s.CustomerCode) Customers,SUM(s.Amount9) Revenue
    FROM f JOIN #sales s ON s.ItemCode=f.ItemCode
      AND s.DocDate>=f.FirstSaleDate AND s.DocDate<DATEADD(month,6,f.FirstSaleDate)
    GROUP BY EOMONTH(f.FirstSaleDate),s.ItemCode;

Truy vấn trên **không** trả lời C34 ("doanh thu SP mới sau 1/3/6/12 tháng so KH; độ phủ khách hàng"):
gộp cả 6 tháng vào một con số nên không tách được theo tuổi, và cửa sổ 6 tháng thì không bao giờ ra
được mốc 12 tháng. SQL dưới đây trả đúng dạng bảng theo tuổi, kèm số khách để đo độ phủ.

**Kiểm duyệt trái — phải loại tháng đầu cửa sổ.** `MIN(DocDate)` chỉ nhìn trong `#sales`, nên mọi mặt
hàng đã bán từ trước `@FromDate` đều bị dồn vào tháng đầu và trông như "sản phẩm mới". Bản chạy tay
của người dùng cho `LaunchMonth` đầu tiên có mã đạt **11.626 khách / 117 tỷ** — không thể là hàng mới
ra mắt. Cột `GhiChu` đánh dấu các dòng này.

**Phần "so KH" (so kế hoạch) chưa làm được**: catalog chỉ có `DIM_TargetSanPhamETC` (chỉ tiêu sản
phẩm **kênh ETC**), không có kế hoạch doanh thu cho sản phẩm mới ở kênh OTC. Cần DNH cấp nguồn kế
hoạch ra mắt sản phẩm thì mới ghép được cột so sánh — không suy ra từ dữ liệu bán.

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

Ô trống ở cột tuổi nghĩa là **tháng đó không phát sinh bán**, không phải chưa đủ tuổi — dùng
`TuoiToiDaDatDuoc` để biết mốc nào đã đánh giá được.

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

    -- !!! KHO LOCAL (warehouse.db, SQLite) - KHONG chay tren Bravo:
    --     Bravo se bao "Invalid object name 'fact_congno_khachhang'".
    SELECT sales_channel,SUM(balance_end) Balance,SUM(total_overdue) Overdue,
           100.0*SUM(total_overdue)/NULLIF(SUM(balance_end),0) OverduePct
    FROM fact_congno_khachhang GROUP BY sales_channel;

    -- !!! KHO LOCAL (warehouse.db, SQLite) - KHONG chay tren Bravo:
    --     Bravo se bao "Invalid object name 'fact_congno_khachhang'".
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

    -- !!! KHO LOCAL (warehouse.db, SQLite) - KHONG chay tren Bravo:
    --     Bravo se bao "Invalid object name 'fact_congno_khachhang'".
    SELECT MIN(snapshot_date) FirstSnapshot,MAX(snapshot_date) LastSnapshot,
           COUNT(DISTINCT snapshot_date) SnapshotCount
    FROM fact_congno_khachhang;

Chỉ được trả chuỗi month-by-month nếu SnapshotCount có đủ các tháng; thiết kế hiện tại đang thay
snapshot cũ bằng snapshot mới.

### S26 — Khách đồng thời giảm mua và nợ xấu — PARTIAL

Chạy trên kho local có attach/mart doanh thu tháng. Nếu chưa có mart doanh thu, dùng S20 xuất danh
sách giảm mua rồi JOIN theo customer_code ngoài SQL.

    -- !!! KHO LOCAL (warehouse.db, SQLite) - KHONG chay tren Bravo:
    --     Bravo se bao "Invalid object name 'fact_congno_khachhang'".
    SELECT TOP (100) d.customer_code,SUM(d.balance_end) Balance,
           SUM(d.total_overdue) Overdue,r.recent_revenue,r.prior_revenue,
           r.recent_revenue-r.prior_revenue RevenueDelta
    FROM fact_congno_khachhang d
    JOIN mart_customer_revenue_compare r ON r.customer_code=d.customer_code
    GROUP BY d.customer_code,r.recent_revenue,r.prior_revenue
    HAVING SUM(d.total_overdue)>0 AND r.recent_revenue<r.prior_revenue
    ORDER BY SUM(d.total_overdue) DESC;

### S27 — Tồn kho snapshot — READY_CURRENT

> ⚠️ **Giá trị tồn thiếu trên diện rộng — không được cộng thành "tổng giá trị tồn kho".** Đo thật
> 03/09/2026 trên `BRV_TonKhoDK` (`IsActive=1`): **B03 (Miền Trung) có 132 mặt hàng, 9.014.691 đơn vị
> nhưng giá trị = 0 đồng**. B02 còn 614 dòng và B04 còn 585 dòng có số lượng > 0 mà `Amount = 0`.
> Nghĩa là con số ~6,26 tỷ đang bị **thiếu hụt ở cả ba chi nhánh**, không riêng Miền Trung. Đây đúng
> câu **A3** đang chờ DNH chốt nguồn giá. Chỉ dùng cột số lượng cho tới khi có nguồn giá.
>
> C41 hỏi "thay đổi thế nào **theo tháng**" — `BRV_TonKhoDK` chỉ là snapshot hiện tại, không có lịch
> sử tồn theo tháng. Chatbot nói rõ giới hạn này là **đúng**, phải chấm ĐẠT.

    SELECT k.BranchCode,p.Code ItemCode,MAX(p.Name) ProductName,
           SUM(t.Quantity) Quantity,SUM(t.Amount) InventoryValue,
           SUM(CASE WHEN ISNULL(t.Amount,0)=0 AND t.Quantity>0 THEN 1 ELSE 0 END) DongThieuGia
    FROM dbo.BRV_TonKhoDK t
    LEFT JOIN dbo.BRV_Kho k ON k.Id=t.WarehouseId
    LEFT JOIN dbo.BRV_SanPham p ON p.Id=t.ItemId
    WHERE t.IsActive=1
    GROUP BY k.BranchCode,p.Code ORDER BY InventoryValue DESC;

Số tháng tồn, chậm luân chuyển và stock-out — phần C41 hỏi mà bảng trên chưa trả lời:

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

Điều kiện lọc phải loại mặt hàng **vừa không tồn vừa không bán** — chúng không phải vấn đề gì, chỉ là
mã cũ nằm trong danh mục. Bản đầu để lọt và gắn nhãn `BINH_THUONG`, gây nhiễu.

⚠️ **Giá trị tồn còn bị ÂM ở một số mã** dù số lượng dương — bản chạy 03/09/2026: `74260010030` tồn
11.048.336 đơn vị nhưng `GiaTriTon = -413.425`; `34140000270` tồn 9.285.200 nhưng `-889.778`. Cộng
với chuyện 1.477 dòng có số lượng mà giá bằng 0, cột `Amount` của `BRV_TonKhoDK` **không dùng làm giá
trị tồn kho được** cho tới khi DNH chốt nguồn giá (câu A3).

### S28 — Cận date và chậm luân chuyển — PARTIAL

Bản trước 03/09/2026 chỉ có script dò cột và kết luận "catalog chưa có ExpiryDate chuẩn". **Kết luận
đó sai** — chính output của script dò cho thấy `BRV_Lot.ExpiryDate` và `BRVSX_Lot.ExpiryDate` đều tồn
tại kiểu `date`. Kiểm thật 03/09/2026: `BRV_Lot` có 3.678/3.740 dòng ghi hạn, `BRVSX_Lot` có
20.738/21.580. Nối `BRV_TonKhoDKLot` với `BRV_Lot` theo khóa kép `(ItemLotCode, ItemId)` đạt **1.599
/1.599 dòng — phủ 100%**, trong đó **824 dòng cận date dưới 6 tháng**. Câu M40/V39 trả lời được.

    SELECT o.name ObjectName,c.name ColumnName,t.name DataType
    FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
    JOIN sys.types t ON t.user_type_id=c.user_type_id
    WHERE (o.name LIKE '%Kho%' OR o.name LIKE '%Lot%')
      AND (c.name LIKE '%Date%' OR c.name LIKE '%Expiry%' OR c.name LIKE '%Han%')
    ORDER BY o.name,c.column_id;

Danh sách lô cần xử lý — cận date hoặc chậm luân chuyển:

    WITH ton AS (
      SELECT t.BranchCode,t.ItemId,t.ItemLotCode,SUM(t.Quantity) Qty,
             MIN(l.ExpiryDate) ExpiryDate
      FROM dbo.BRV_TonKhoDKLot t
      LEFT JOIN dbo.BRV_Lot l ON l.ItemLotCode=t.ItemLotCode AND l.ItemId=t.ItemId
      WHERE t.IsActive=1 AND t.Quantity>0
      GROUP BY t.BranchCode,t.ItemId,t.ItemLotCode
    ), ban AS (
      SELECT ItemCode,SUM(CASE WHEN UnitPrice>0 THEN Quantity ELSE 0 END)/3.0 QtyPerMonth
      FROM #sales WHERE DocDate>=DATEADD(month,-3,@MonthEnd) AND DocDate<@MonthEnd
      GROUP BY ItemCode
    ), x AS (
      SELECT ton.BranchCode,p.Code ItemCode,MAX(p.Name) ProductName,ton.ItemLotCode,
             ton.Qty,ton.ExpiryDate,MAX(ban.QtyPerMonth) QtyPerMonth
      FROM ton
      LEFT JOIN dbo.BRV_SanPham p ON p.Id=ton.ItemId
      LEFT JOIN ban ON ban.ItemCode=p.Code
      GROUP BY ton.BranchCode,p.Code,ton.ItemLotCode,ton.Qty,ton.ExpiryDate
    )
    SELECT BranchCode,ItemCode,ProductName,ItemLotCode,Qty,ExpiryDate,
           DATEDIFF(day,@AsOfDate,ExpiryDate) SoNgayConHan,
           CASE WHEN ExpiryDate IS NULL THEN 'KHONG_CO_HAN'
                WHEN ExpiryDate<@AsOfDate THEN 'DA_HET_HAN'
                WHEN ExpiryDate<DATEADD(month,3,@AsOfDate) THEN 'CAN_DATE_DUOI_3_THANG'
                WHEN ExpiryDate<DATEADD(month,6,@AsOfDate) THEN 'CAN_DATE_3_6_THANG'
                ELSE 'CON_HAN' END NhomHan,
           QtyPerMonth,Qty/NULLIF(QtyPerMonth,0) SoThangTon,
           CASE WHEN ISNULL(QtyPerMonth,0)=0 THEN 'KHONG_BAN_3_THANG_GAN_NHAT'
                WHEN Qty/NULLIF(QtyPerMonth,0)>6 THEN 'CHAM_LUAN_CHUYEN'
                ELSE 'BINH_THUONG' END NhomLuanChuyen
    FROM x
    WHERE ExpiryDate<DATEADD(month,6,@AsOfDate)
       OR ISNULL(QtyPerMonth,0)=0
       OR Qty/NULLIF(QtyPerMonth,0)>6
    ORDER BY CASE WHEN ExpiryDate<@AsOfDate THEN 0
                  WHEN ExpiryDate<DATEADD(month,3,@AsOfDate) THEN 1 ELSE 2 END,
             Qty DESC;

**PARTIAL vì hai lý do còn lại:**
- Không quy ra tiền được cho toàn bộ tồn — xem ghi chú giá trị tồn ở `S27`.
- `BRVSX_Lot` có hạn dùng sai định dạng (`MIN(ExpiryDate)` ra **1029-10-16**, gõ nhầm năm). Truy vấn
  trên chỉ dùng `BRV_Lot`; nếu mở rộng sang `BRVSX_` phải lọc năm hợp lệ trước.
- Ngưỡng 6 tháng tồn cho "chậm luân chuyển" là đề xuất của MCNA, cần DNH chốt.

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

**Không có dữ liệu đấu thầu trong Bravo — đã kiểm hết catalog 03/09/2026.** Tìm mọi đối tượng
(`USER_TABLE`/`VIEW`) khớp `%Thau%`, `%Tender%`, `%Bid%`, `%HopDong%` chỉ ra **4 đối tượng, tất cả
đều là hợp đồng đã ký**: `vHopDongETC`, `DMSSX_HopDongHdr`, `DMSSX_HopDongCt`, `FACT_DuDKHopDongETC`.
Không có bảng nào ghi kế hoạch thầu, giá trị tham gia, hay kết quả trúng/trượt.

`StatusId` **không** phân biệt trúng/trượt: chỉ có 2 giá trị trên 8.607 hợp đồng (1: 1.834 HĐ,
2: 6.773 HĐ). Hợp đồng là thứ đã KÝ — không suy ngược ra được gói nào đã dự mà trượt.

Vì vậy **chatbot từ chối C43/M41 là hành vi đúng**: giá trị tham gia thầu, giá trị trúng và tỷ lệ
trúng đều không có nguồn. Muốn trả lời phải được DNH cấp dữ liệu đấu thầu (nhiều khả năng đang nằm ở
file Excel của bộ phận thầu, chưa đồng bộ vào Bravo).

⚠️ **Hai hợp đồng có giá trị sai lệch nghiêm trọng, phải loại trước khi cộng bất kỳ tổng nào:**

| ContractId | DocNo | AmountBefVat | Ghi chú |
|---|---|---:|---|
| 115627 | `225/HĐKT-NH` | 2.952.380.952.390.000 | 2,95 **triệu tỷ** trên đúng 1 dòng |
| 112468 | `38/NH-TTYTKRP-GL` | 56.934.879.059.072 | 56,9 nghìn tỷ trên 4 dòng |

Hợp đồng bình thường nằm trong khoảng 2–50 tỷ. Hai dòng này chiếm gần như toàn bộ con số tổng
3 triệu tỷ, rõ ràng là lỗi nhập liệu. Cả hai hết hạn từ 2022–2023 nên **không lọt vào `S86`** (đã lọc
`FromDate>=@FromDate`), nhưng bất kỳ truy vấn nào không lọc kỳ sẽ bị bóp méo.

`AmountBefVat` là giá trị **theo dòng** (kiểm HĐ 119349: 148 dòng, 33 giá trị khác nhau), không phải
giá trị header lặp lại — nên `SUM` theo `Id0` là đúng.

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

Bảng trên trả **% hoàn thành của tổng doanh thu** — đó KHÔNG phải điều C45 hỏi. C45 hỏi **tỷ lệ NHÂN
SỰ** đạt từng mốc, tức đếm người rồi chia, không phải cộng tiền rồi chia. Hai chỉ số này lệch nhau
rất xa: một đội có vài người vượt xa chỉ tiêu vẫn ra "tổng đạt 100%" trong khi phần lớn nhân sự dưới
mốc.

Chỉ đếm người **có target > 0**. Đo thật T8/2026: 209 bản ghi thì 17 có target NULL hoặc 0 — giữ lại
sẽ kéo tỷ lệ xuống sai vì họ không có mốc để so.

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

**Cổng 65%/70% không phải "đạt KPI"** — đó là mốc bắt đầu được thưởng nhóm hàng (TDV 65%, các vị trí
khác 70%, theo QĐ 0107/2026 và QĐ 0429/.25). "Đạt chỉ tiêu" là ≥100%. Đừng gộp hai khái niệm.

**Nguồn này chỉ phủ kênh OTC** — chưa có KPI cá nhân cho ETC (câu A5 chờ DNH). Ngoài ra 9 bản ghi có
tên dạng "QLV ..." nhưng `PositionCode='TDV'` (T8/2026), cùng loại nghi vấn với `MBKV12` ở câu A4.

**Lệch mẫu số với chatbot — cần chốt "nhân sự được tính" gồm ai.** Đối chiếu T8/2026:

| Chức danh | Chatbot | Checker (Bravo) |
|---|---|---|
| TDV | **146** người · 122 · 66 · 30 · 11 | **158** người · 122 · 66 · 30 · 11 |
| QLV | 19 · 14 · 9 · 4 · 0 | 21 · 16 · 11 · 5 · 1 |
| CS | 3 | 4 |
| CTV | 2 | 3 |

**Tử số TDV khớp tuyệt đối cả bốn mốc** — tức hai bên tính cùng một cách, chỉ khác tập người được
đếm. Chatbot lấy tổng 171 người, checker lấy 192 (mọi bản ghi có `MonthSaleTarget>0`), chênh 21
người. Vì 12 TDV bị loại đều nằm dưới mọi mốc nên tỷ lệ qua cổng đội lên **83,6%** thay vì **77,2%** —
chênh 6,4 điểm chỉ do mẫu số.

Không kết luận bên nào sai khi chưa biết chatbot lọc theo tiêu chí gì. Nếu 21 người đó thật sự không
thuộc lực lượng bán OTC thì chatbot đúng; nếu họ là nhân sự thật chỉ đang dưới chuẩn thì loại ra là
làm đẹp số. **Cần xem `audit_log` phiên hỏi C45, hoặc DNH chốt định nghĩa "nhân sự được tính".**

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

> ⚠️ **KHÔNG cộng cột `Revenue` của bảng trên qua các chức danh.** Tầng quản lý là rollup của tầng
> nhân viên nên doanh thu bị lặp: bản chạy T8/2026 cho `QLV` và `TP` của Miền Bắc cùng đúng một con số
> 28.469.978.376. Cộng tất cả chức danh ra 155,9 tỷ trong khi doanh thu thật của lực lượng bán chỉ
> **48,9 tỷ** — đội gấp hơn 3 lần.
>
> **Thưởng thì ngược lại: KHÔNG bị trùng** (mỗi người một khoản riêng), nên tổng thưởng 1.060.518.990
> là đúng. Vì vậy tỷ lệ chi phí thưởng phải lấy **tổng thưởng mọi chức danh chia cho doanh thu tầng
> nhân viên**: `1.060.518.990 / 48.922.979.422` = **2,168%**. Lấy nhầm mẫu số 155,9 tỷ sẽ ra 0,680%,
> thấp hơn thực tế hơn 3 lần.

Tỷ lệ chi phí thưởng ở cấp công ty, tính đúng mẫu số:

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    ), k AS (
      SELECT EOMONTH(SaveDate) MonthEnd,PositionCode,MonthSaleAmount,
             ISNULL(DMBonus,0)+ISNULL(V15Bonus,0)+ISNULL(V22Bonus,0)
            +ISNULL(V25Bonus,0)+ISNULL(ASOBonus,0) Bonus
      FROM b WHERE SnapshotRank=1
        AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
    )
    SELECT MonthEnd,
      SUM(CASE WHEN PositionCode IN ('TDV','CTV','CS','TK')
               THEN MonthSaleAmount ELSE 0 END) DoanhThuTangNhanVien,
      SUM(Bonus) TongThuongMoiChucDanh,
      SUM(CASE WHEN PositionCode IN ('TDV','CTV','CS','TK') THEN Bonus ELSE 0 END) ThuongTangNhanVien,
      SUM(CASE WHEN PositionCode NOT IN ('TDV','CTV','CS','TK') THEN Bonus ELSE 0 END) ThuongTangQuanLy,
      100.0*SUM(Bonus)/NULLIF(SUM(CASE WHEN PositionCode IN ('TDV','CTV','CS','TK')
                                       THEN MonthSaleAmount ELSE 0 END),0) TyLeThuongTrenDoanhThuPct
    FROM k GROUP BY MonthEnd ORDER BY MonthEnd;

**Chatbot từ chối C48 với hai lý do, chỉ một lý do là hạn chế dữ liệu thật:**
- *Lợi nhuận không có nguồn* — **đúng**, cùng gốc với `S10` (không có giá vốn hàng bán). Phần "thưởng
  trên lợi nhuận" của C48 không trả lời được.
- *Không có công cụ tổng hợp thưởng toàn công ty* (chỉ có tool xếp hạng TOP 100 nên bỏ sót ~106 người)
  — đây là **thiếu công cụ, không phải thiếu dữ liệu**. Truy vấn trên tính được tổng ngay từ Bravo.
  Chatbot thà từ chối còn hơn cộng TOP 100 rồi gọi là tổng — quyết định đúng, nhưng khoảng trống này
  vá được bằng cách bổ sung tool tổng hợp.

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

> 🔴 **Dữ liệu viếng thăm CÓ THẬT trên Bravo nhưng CHƯA đồng bộ xuống kho chatbot — đây là khoảng
> trống ETL, không phải thiếu nguồn.** Kiểm 03/09/2026: `dbo.DMS_DiTuyen` có **1.785.213 dòng**, 451
> nhân viên, 37.853 khách, trải từ **06/06/2022 đến 03/09/2026 (hôm nay)**. Trong `warehouse.db` thì
> **không có bảng nào** về tuyến/viếng thăm (đã quét cả 24 bảng).
>
> Vì vậy chatbot từ chối C49 là **hợp lý với quyền truy cập của nó**, nhưng hai lý do nó đưa ra đều
> sai: (1) nói đã tìm trong "catalog SQL Server Bravo" mà không thấy — bảng nằm ngay đó; (2) suy đoán
> "dữ liệu từ app DMS/SFA riêng" — không phải, nó ở trong chính Bravo.
>
> Bảng còn có `IsPlaned` (viếng thăm theo tuyến hay ngoài tuyến) và `ArriveTime`/`LeaveTime`
> (check-in/check-out) — tức **cả bốn chỉ số C49 hỏi đều tính được**, kể cả độ phủ tuyến mà chatbot
> nói là không có. Đồng bộ bảng này xuống kho là mở khoá được nguyên nhóm câu hỏi.

Đủ bốn chỉ số C49 — độ phủ tuyến, lượt viếng thăm, tỷ lệ có đơn, doanh thu mỗi lượt:

    WITH v AS (
      SELECT DocDate,EmpDMSCode,CustomerCode,IsPlaned
      FROM dbo.DMS_DiTuyen WHERE DocDate>=@FromDate AND DocDate<@ToDate
    ), o AS (
      SELECT DISTINCT DocDate,DMSEmpId1 EmpDMSCode,CustomerCode
      FROM dbo.DMS_DonHangHdr WHERE DocDate>=@FromDate AND DocDate<@ToDate
    ), rev AS (
      SELECT EOMONTH(DocDate) MonthEnd,EmpDMSCode,SUM(Amount9) Revenue
      FROM #sales GROUP BY EOMONTH(DocDate),EmpDMSCode
    )
    SELECT EOMONTH(v.DocDate) MonthEnd,v.EmpDMSCode,
      COUNT(*) LuotVieng,
      COUNT(DISTINCT v.CustomerCode) KhachDuocVieng,
      SUM(CASE WHEN v.IsPlaned=1 THEN 1 ELSE 0 END) LuotTheoTuyen,
      100.0*SUM(CASE WHEN v.IsPlaned=1 THEN 1 ELSE 0 END)/NULLIF(COUNT(*),0) TyLeTheoTuyenPct,
      SUM(CASE WHEN o.CustomerCode IS NOT NULL THEN 1 ELSE 0 END) LuotCoDon,
      100.0*SUM(CASE WHEN o.CustomerCode IS NOT NULL THEN 1 ELSE 0 END)
        /NULLIF(COUNT(*),0) TyLeCoDonPct,
      MAX(rev.Revenue) DoanhThuThang,
      MAX(rev.Revenue)/NULLIF(COUNT(*),0) DoanhThuMoiLuotVieng
    FROM v
    LEFT JOIN o ON o.DocDate=v.DocDate AND o.EmpDMSCode=v.EmpDMSCode
      AND o.CustomerCode=v.CustomerCode
    LEFT JOIN rev ON rev.MonthEnd=EOMONTH(v.DocDate) AND rev.EmpDMSCode=v.EmpDMSCode
    GROUP BY EOMONTH(v.DocDate),v.EmpDMSCode
    ORDER BY MonthEnd DESC,TyLeCoDonPct;

**Tỷ lệ có đơn ở đây là cận dưới, không phải con số tuyệt đối.** Phép nối đòi khớp đồng thời cả ba:
cùng ngày, cùng nhân viên, cùng khách. Đơn đặt sau buổi thăm vài ngày sẽ không được tính, nên chỉ số
này thấp hơn thực tế. Muốn đo đúng phải chốt với DNH khoảng thời gian hợp lệ giữa lượt thăm và đơn
(ví dụ trong 3 ngày) — đây là điểm cần thêm vào nhóm câu hỏi nghiệp vụ.

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
      FROM dbo.DMS_DonHangCTKM x LEFT JOIN dbo.DMS_DonHangHdr h ON h.Id=x.OrderId
    UNION ALL SELECT 'VIENG_THAM',MAX(DocDate),MAX(SyncAt) FROM dbo.DMS_DiTuyen;

> 🔴 **Đồng bộ khuyến mãi đã DỪNG từ 09/01/2026 — phát hiện 03/09/2026, tức đứng yên 8 tháng.**
> Bảng liên kết `DMS_DonHangCTKM` có `MAX(SyncAt)` và `MAX(DocDate)` đều là 09/01/2026, trong khi mọi
> nguồn khác đều cập nhật tới hôm nay. Đếm đơn gắn CTKM theo tháng cho thấy rõ điểm gãy:
>
> | Tháng | Đơn gắn CTKM |
> |---|---:|
> | 09–12/2025 | 12.447 – 13.545 mỗi tháng |
> | 01/2026 | **2.042** (dừng giữa tháng) |
> | 02/2026 trở đi | **0** |
>
> Hệ quả: **C18, M35, V34 chỉ trả lời được tới đầu 01/2026**, không có dữ liệu khuyến mãi cho 8 tháng
> gần nhất. Mọi câu hỏi "chương trình nào hiệu quả" cho kỳ 2026 sẽ rỗng. Đây là **sự cố vận hành cần
> khôi phục sync**, không phải giới hạn thiết kế — và là lý do chính khiến checker này tồn tại.

Truy vấn trên đã bổ sung dòng `VIENG_THAM`: `DMS_DiTuyen` cập nhật tới hôm nay trên Bravo (xem `S34`),
nên đối chiếu freshness sẽ lộ ngay việc bảng này chưa được đưa xuống kho local.

**Chatbot báo "không lấy được mốc khuyến mãi do timeout"** — checker lấy được bình thường, nên đó là
vấn đề phía công cụ chứ không phải nguồn. Nhưng kết quả cuối cùng vẫn đúng hướng: mốc khuyến mãi thật
sự có vấn đề, chỉ khác nguyên nhân.

### S38 — Chất lượng mapping, target và snapshot — READY

> ⚠️ **Cột `MissingManager` của truy vấn đầu là dương tính giả gần như hoàn toàn.** Đo T8/2026 trên
> `FACT_ThongKeTinhLuong`: tầng nhân viên (TDV/CTV/CS/TK, 183 người) có **0 người thiếu quản lý**;
> toàn bộ 26 ca "thiếu" đều là **chính các quản lý** (TP/QLV/PP) — không có cấp trên trong trường đó
> là đúng cấu trúc, không phải lỗi mapping. Phải tách tầng trước khi đếm, nếu không sẽ báo động giả
> mỗi tháng.
>
> **Snapshot tháng đang chạy dở cũng gây hiểu nhầm.** Ngày 03/09/2026 `FACT_TongHopKhachHang` mới có
> **16 nhân viên** (sync tháng 9 vừa bắt đầu) so với 186 của tháng 8 trọn vẹn. Chatbot báo "6 nhân sự
> thiếu quản lý" chính là 6/16 của snapshot dở dang — đúng số học nhưng đọc thành 6/200 thì sai hẳn
> quy mô. Luôn đối chiếu cột `Employees` trước khi diễn giải các cột lỗi.

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

Đếm đúng theo tầng — chỉ tầng nhân viên mới coi thiếu quản lý là lỗi:

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    )
    SELECT EOMONTH(SaveDate) MonthEnd,
      CASE WHEN PositionCode IN ('TDV','CTV','CS','TK') THEN 'Tang nhan vien'
           ELSE 'Tang quan ly' END Tang,
      COUNT(*) SoNguoi,
      SUM(CASE WHEN ManagerCode IS NULL OR ManagerCode='' THEN 1 ELSE 0 END) ThieuQuanLy,
      SUM(CASE WHEN MonthSaleTarget IS NULL OR MonthSaleTarget<=0 THEN 1 ELSE 0 END) ThieuTarget,
      SUM(CASE WHEN (MonthSaleTarget IS NULL OR MonthSaleTarget<=0)
                AND MonthSaleAmount>0 THEN 1 ELSE 0 END) CoDoanhSoMaThieuTarget
    FROM b WHERE SnapshotRank=1
      AND (@AreaCode IS NULL OR AreaCode=@AreaCode)
    GROUP BY EOMONTH(SaveDate),
      CASE WHEN PositionCode IN ('TDV','CTV','CS','TK') THEN 'Tang nhan vien' ELSE 'Tang quan ly' END
    ORDER BY MonthEnd DESC,Tang;

Danh sách TỪNG NGƯỜI có vấn đề — C54 và V17 hỏi "nhân viên nào", nên phải có mã kèm **tên**:

    WITH b AS (
      SELECT *,DENSE_RANK() OVER(
        PARTITION BY EOMONTH(SaveDate), EmployeeCode ORDER BY SaveDate DESC) SnapshotRank
      FROM dbo.FACT_ThongKeTinhLuong
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate
    )
    SELECT EOMONTH(b.SaveDate) MonthEnd,b.EmployeeCode,b.EmployeeName,b.PositionCode,
           b.AreaCode,b.ManagerCode,b.MonthSaleAmount,b.MonthSaleTarget,
           CASE WHEN b.MonthSaleAmount>0 THEN 'CO_DOANH_SO_NHUNG_THIEU_TARGET'
                WHEN b.EmployeeName LIKE N'%QLV%' THEN 'NGHI_TRUNG_BAN_GHI_QLV'
                WHEN b.EmployeeCode LIKE 'TRONGTDV%' THEN 'VI_TRI_TRONG'
                ELSE 'THIEU_TARGET' END LoaiVanDe,
           n.IsDuplicate
    FROM b LEFT JOIN dbo.DIM_NhanVien n ON n.EmployeeCode=b.EmployeeCode
    WHERE b.SnapshotRank=1
      AND b.PositionCode IN ('TDV','CTV','CS','TK')
      AND ((b.ManagerCode IS NULL OR b.ManagerCode='')
           OR b.MonthSaleTarget IS NULL OR b.MonthSaleTarget<=0)
      AND (@AreaCode IS NULL OR b.AreaCode=@AreaCode)
    ORDER BY MonthEnd DESC,LoaiVanDe,b.EmployeeCode;

**Ba nhóm lộ ra khi chạy T8/2026 (17 người), rất khác nhau về mức nghiêm trọng:**

- **10 bản ghi trùng của chính QLV** — `.QLV5 Vũ Anh Hiếu (QLV)`, `ASM03 Nguyễn Văn Danh (QLV)`,
  `DNH00601 Vũ Xuân Phong (QLV)`… Cùng người đã có mặt ở tầng quản lý (`MBKV9`, `TM23100148`,
  `TM25010129`…) nhưng lại có thêm một bản ghi `PositionCode='TDV'`, doanh số 0, không target. Đây
  đúng loại nghi vấn `MBKV12` ở câu **A4**. Vài mã còn có dấu chấm cuối (`TM24050201.`,
  `TM25030101.`) — dấu hiệu nhân bản mã.
- **4 vị trí trống** (`TRONGTDV2/4/5/6`) đặt tên theo QLV đang gánh. `TRONGTDV2` có doanh số
  19.729.100 nhưng không target.
- **3 TDV thật sự thiếu target**: `TM25010167`, `TM25090401`, `TM26060104`; riêng `TM25031901`
  (Nguyễn Quốc Chiến) có doanh số 4.180.953 mà không có chỉ tiêu — đây là ca cần xử lý sớm nhất.

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

Bản trước 03/09/2026 có ba lỗi, đã sửa cả ba — ghi lại để không tái phạm:

1. **Gọi `IsAC` là `ActiveCustomers`.** `IsAC` chỉ dành cho CS (Chợ sỉ) và TK (kênh MT) theo DNH chốt
   27/08/2026, nên với TDV nó bằng 0 — bản chạy cũ có `ActiveCustomers=0` ở hầu hết dòng và
   `RevenuePerActiveCustomer` rỗng theo. Đây đúng lỗi đã sửa trong chatbot ngày 26/08 (`02c3e0c`);
   để nguyên trong bộ đáp án thì đáp án lại mâu thuẫn với chính chatbot đã vá.
2. **Trộn hai tầng QLV và TDV trong cùng một bảng.** Bản cũ cho `MN1` (QLV) và `TM23100133` (TDV dưới
   quyền) cùng doanh thu 4.713.095.264 — cộng ngang là gấp đôi. Nay lọc đúng tầng nhân viên.
3. **Không trả lời câu hỏi V14** ("ai có nhiều khách phụ trách nhưng tỷ lệ khách mua thấp") — bản cũ
   chỉ xếp theo doanh thu giảm dần, người đọc phải tự dò 2.280 dòng.

"Khách có mua" đo bằng `Amount_CT>0`, không dùng cờ `IsAC`.

    WITH snaps AS (
      SELECT EOMONTH(SaveDate) MonthEnd,MAX(SaveDate) SaveDate
      FROM dbo.FACT_TongHopKhachHang
      WHERE SaveDate>=@FromDate AND SaveDate<@ToDate GROUP BY EOMONTH(SaveDate)
    ), x AS (
      SELECT EOMONTH(f.SaveDate) MonthEnd,f.EmployeeCode,f.ManagerCode,
             MAX(n.PositionCode) PositionCode,
             COUNT(DISTINCT f.CustomerCode) AssignedCustomers,
             COUNT(DISTINCT CASE WHEN f.Amount_CT>0 THEN f.CustomerCode END) PurchasingCustomers,
             COUNT(DISTINCT CASE WHEN f.IsNC=1 THEN f.CustomerCode END) NewCustomers,
             COUNT(DISTINCT CASE WHEN f.IsRO=1 THEN f.CustomerCode END) ReorderCustomers,
             COUNT(DISTINCT CASE WHEN f.IsAC=1 THEN f.CustomerCode END) IsAC_ChiCS_TK,
             SUM(f.Amount_CT) Revenue
      FROM dbo.FACT_TongHopKhachHang f
      JOIN snaps s ON s.SaveDate=f.SaveDate
      JOIN dbo.DIM_NhanVien n ON n.EmployeeCode=f.EmployeeCode
      WHERE n.PositionCode IN ('TDV','CTV','CS','TK')
        AND (@ManagerCode IS NULL OR f.ManagerCode=@ManagerCode)
      GROUP BY EOMONTH(f.SaveDate),f.EmployeeCode,f.ManagerCode
    ), r AS (
      SELECT *,100.0*PurchasingCustomers/NULLIF(AssignedCustomers,0) TyLeKhachMuaPct,
             Revenue/NULLIF(PurchasingCustomers,0) RevenuePerPurchasingCustomer,
             PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY AssignedCustomers)
               OVER(PARTITION BY MonthEnd) MedianAssigned
      FROM x
    )
    SELECT MonthEnd,EmployeeCode,ManagerCode,PositionCode,
           AssignedCustomers CustomersInSnapshot,
           PurchasingCustomers,TyLeKhachMuaPct,NewCustomers,ReorderCustomers,
           IsAC_ChiCS_TK,Revenue,RevenuePerPurchasingCustomer
    FROM r
    ORDER BY MonthEnd DESC,Revenue DESC;

⚠️ Cột `CustomersInSnapshot` ở trên **không phải "khách phụ trách"** — `FACT_TongHopKhachHang` chỉ
chứa khách ĐÃ phát sinh, nên tỷ lệ mua tính từ nó luôn xấp xỉ 100% và không phân biệt được ai. Đo
thật T8/2026: 165 nhân viên, thấp nhất **96,4%**, trung bình **99,9%**, **không một ai** dưới 90%.
Đừng dùng cột này để trả lời V14.

Danh sách khách phụ trách thật nằm ở `DMS_KhachHang.EmpDMSCode1` (`IsActive=1`). Dùng nguồn đó thì
chỉ số mới có ý nghĩa — cùng tháng 8/2026: 161 nhân viên, từ **0%** đến **100%**, trung bình
**31,8%**, có **142 người dưới 50%**; tổng khách được phân công 25.336 so với khoảng 7.000 khách phát
sinh mỗi tháng.

**Giới hạn**: `DMS_KhachHang` là danh sách hiện tại, không có lịch sử phân công, nên chỉ tính đúng
cho kỳ gần nhất — không truy ngược các tháng trước.

    WITH book AS (
      SELECT EmpDMSCode1 EmpDMS,COUNT(DISTINCT Code) KhachPhanCong
      FROM dbo.DMS_KhachHang
      WHERE EmpDMSCode1 IS NOT NULL AND LTRIM(RTRIM(EmpDMSCode1))<>'' AND IsActive=1
      GROUP BY EmpDMSCode1
    ), mua AS (
      SELECT k.EmpDMSCode1 EmpDMS,COUNT(DISTINCT s.CustomerCode) KhachCoMua,
             SUM(s.Amount9) DoanhThu
      FROM #sales s JOIN dbo.DMS_KhachHang k ON k.Code=s.CustomerCode
      WHERE s.DocDate>=@MonthStart AND s.DocDate<@MonthEnd
      GROUP BY k.EmpDMSCode1
    )
    SELECT n.EmployeeCode,n.Name EmployeeName,n.PositionCode,n.AreaCode,
           b.KhachPhanCong,ISNULL(m.KhachCoMua,0) KhachCoMua,
           100.0*ISNULL(m.KhachCoMua,0)/NULLIF(b.KhachPhanCong,0) TyLeKhachMuaPct,
           ISNULL(m.DoanhThu,0) DoanhThu,
           b.KhachPhanCong-ISNULL(m.KhachCoMua,0) KhachChuaMua
    FROM book b
    LEFT JOIN mua m ON m.EmpDMS=b.EmpDMS
    LEFT JOIN dbo.DIM_NhanVien n ON n.DMSId=b.EmpDMS
    WHERE (@ManagerCode IS NULL OR n.ManagerAreaCode=@ManagerCode)
    ORDER BY b.KhachPhanCong DESC,TyLeKhachMuaPct;

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
| C13 | Doanh thu gộp, chiết khấu, khuyến mãi, hàng trả và doanh thu thuần từng tháng là bao nhiêu? | S87 | PARTIAL |
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
| C25 | Năng suất mỗi NPP/chi nhánh theo tháng là bao nhiêu; NPP nào doanh thu giảm, tồn kho tăng hoặc công nợ xấu đi? | S15 | PARTIAL |
| C26 | Khách mua đồng thời OTC và ETC đóng góp bao nhiêu doanh thu/công nợ; xu hướng mua chéo kênh ra sao? | S16 | READY |
| C27 | Có sự dịch chuyển doanh thu bất thường giữa kênh, miền, chi nhánh hoặc mã nhân viên qua các tháng không? | S17 | PARTIAL |
| C28 | Nếu loại ảnh hưởng của thay đổi địa bàn, chuyển nhân viên và chuyển khách, tăng trưởng thực của từng đơn vị còn bao nhiêu? | S17 | PARTIAL |
| C29 | Số khách hoạt động, khách mới, khách mua lại, khách tái kích hoạt và khách ngừng mua từng tháng là bao nhiêu? | S18 | READY |
| C30 | Tỷ lệ giữ chân khách theo cohort tháng mở mới sau 1/3/6/12 tháng là bao nhiêu, theo kênh và miền? | S19 | DERIVED |
| C31 | Doanh thu mất đi từ khách ngừng mua và doanh thu tăng thêm từ khách mới/tái kích hoạt bù được bao nhiêu? | S20 | READY |
| C32 | Top khách hàng tăng/giảm mạnh nhất từng tháng là ai; thay đổi đó ảnh hưởng bao nhiêu đến toàn công ty? | S71 | READY |
| C33 | Nhóm sản phẩm/SKU nào là động lực tăng trưởng, nhóm nào kéo giảm tăng trưởng và nhóm nào mất thị phần nội bộ? | S21 | PARTIAL |
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
| M29 | NPP/chi nhánh nào có tăng trưởng khách hàng tốt nhưng công nợ hoặc tồn kho xấu đi? | S15 | PARTIAL |
| M30 | Danh sách 20 khách hàng ưu tiên cần giữ, thu hồi, tái kích hoạt hoặc mở rộng trong tháng tới là ai? | S48 | DERIVED |
| M31 | Nhóm sản phẩm/SKU nào đóng góp nhiều nhất vào tăng/giảm của miền/kênh theo tháng? | S21 | PARTIAL |
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
| V29 | Top/bottom sản phẩm từng tháng của đội; SKU nào làm tăng/giảm doanh số nhiều nhất? | S21 | PARTIAL |
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
