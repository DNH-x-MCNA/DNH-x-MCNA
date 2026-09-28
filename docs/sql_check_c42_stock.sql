-- C42: doi chieu doanh thu giam voi TON THEO LO HE KINH DOANH (TM).
-- Chay tren Bravo (chi doc), sau khi #sales da duoc nap cung pham vi doanh thu voi chatbot.
-- @AsOfStockDate phai la ngay du lieu ton cua lan dong bo chatbot, khong phai ngay cuoi ky ban.
-- Chatbot get_sku_revenue_drop_vs_stock mac dinh: hai ky 3 thang tron, ky moi 06-08/2026
-- neu chay trong 09/2026; min_prev_revenue=50 trieu, giam >=30%.
-- Dat @DropPctThreshold=0 neu muon xem MOI SKU giam nhu query kiem tra ban dau.
-- Tong hai ky khong chung minh doanh thu giam lien tuc tung thang.

DECLARE @AsOfStockDate date = '2026-09-28';
DECLARE @FiscalYear int = YEAR(@AsOfStockDate);
DECLARE @MinPrevRevenue decimal(18, 2) = 50000000;
DECLARE @DropPctThreshold decimal(9, 2) = 30;

WITH revenue_by_period AS (
    SELECT ItemCode,
           SUM(CASE WHEN DocDate >= '2026-03-01' AND DocDate < '2026-06-01'
                    THEN Amount9 ELSE 0 END) PrevRevenue,
           SUM(CASE WHEN DocDate >= '2026-06-01' AND DocDate < '2026-09-01'
                    THEN Amount9 ELSE 0 END) CurRevenue
    FROM #sales
    WHERE DocDate >= '2026-03-01' AND DocDate < '2026-09-01'
    GROUP BY ItemCode
), stock_ledger AS (
    -- BRV_TonKhoDKLot la TON DAU NAM, khong phai ton hien tai.
    SELECT t.WarehouseId, p.Code ItemCode, t.ItemLotCode,
           SUM(t.Quantity) Qty
    FROM dbo.BRV_TonKhoDKLot t
    JOIN dbo.BRV_SanPham p ON p.Id = t.ItemId
    WHERE t.IsActive = 1 AND t.[Year] = @FiscalYear
    GROUP BY t.WarehouseId, p.Code, t.ItemLotCode
    UNION ALL
    -- Dong bo local cong bien dong TM theo kho + SKU + lo den ngay chot ton.
    SELECT k.Id WarehouseId, p.Code ItemCode, v.ItemLotCode,
           SUM(v.ReceiptQuantity - v.IssueQuantity) Qty
    FROM dbo.vTheKhoLot v
    JOIN dbo.BRV_Kho k ON k.Code = v.WarehouseCode
    JOIN dbo.BRV_SanPham p ON p.Id = v.ItemId
    WHERE v.ClassCode = 'TM' AND v.FiscalYear = @FiscalYear
      AND v.DocDate <= @AsOfStockDate
      AND v.ItemLotCode IS NOT NULL AND v.ItemLotCode <> ''
    GROUP BY k.Id, p.Code, v.ItemLotCode
), closing_by_lot AS (
    SELECT WarehouseId, ItemCode, ItemLotCode, SUM(Qty) Qty
    FROM stock_ledger
    GROUP BY WarehouseId, ItemCode, ItemLotCode
), stock AS (
    SELECT ItemCode, SUM(Qty) StockQtyTM
    FROM closing_by_lot
    GROUP BY ItemCode
), compare AS (
    SELECT r.ItemCode, p.ItemName, r.PrevRevenue, r.CurRevenue,
           100.0 * (r.PrevRevenue - r.CurRevenue) / NULLIF(r.PrevRevenue, 0) DropPct,
           s.StockQtyTM
    FROM revenue_by_period r
    LEFT JOIN stock s ON s.ItemCode = r.ItemCode
    LEFT JOIN (SELECT Code, MAX(Name) ItemName FROM dbo.BRV_SanPham GROUP BY Code) p
      ON p.Code = r.ItemCode
    WHERE r.PrevRevenue >= @MinPrevRevenue AND r.CurRevenue < r.PrevRevenue
)
SELECT ItemCode [Ma SKU], ItemName [Ten], PrevRevenue [DT ky truoc], CurRevenue [DT ky nay],
       ROUND(DropPct, 1) [Giam (%)], StockQtyTM [Ton TM theo lo cuoi ky],
       CASE WHEN StockQtyTM IS NULL OR StockQtyTM < 0 THEN 'unknown_or_negative_stock'
            WHEN StockQtyTM = 0 THEN 'zero_recorded_stock'
            ELSE 'positive_recorded_stock' END [Nhom chatbot]
FROM compare
WHERE DropPct >= @DropPctThreshold
ORDER BY [Nhom chatbot], [Ma SKU];

-- Khong cong BRVSX_TonKhoDK vao StockQtyTM: do la he san xuat (SX), khac nguon
-- get_sku_revenue_drop_vs_stock. So luong ton va so luong ban co the khac don vi;
-- ton duong khong tu chung minh ton cao, va doanh thu giam khong chung minh mat don.
