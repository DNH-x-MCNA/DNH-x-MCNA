USE [NH_Report_TM]
GO
/****** Object:  StoredProcedure [dbo].[usp_StockLotFinance_Report]    Script Date: 7/17/2026 10:39:13 AM ******/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
--Thủ tục tính khách hàng không active:
ALTER PROC [dbo].[usp_StockLotFinance_Report]
  @_DocDate DATE = '2026-03-31',
  @_SaleVelocityNum INT = 6,
  @_ExpiryPeriod INT = 3,
  @_ExpiryDays INT = 180,
  @_NearExpiryDays INT = 540,
  @_OutOfStockMonth INT = 1,
  @_ShortOfStockMonth INT = 6,
  @_RepType INT = 1,
  @_WarehouseCodeNotIncluded VARCHAR(3000) = ''
AS
BEGIN
	SET NOCOUNT ON
	DECLARE @_DocDate1 DATE, @_DocDate2 DATE, @_DocDate0 DATE
	SET @_DocDate2 = DATEADD(D, -1, DATEFROMPARTS(YEAR(@_DocDate), MONTH(@_DocDate), 1))
	SET @_DocDate1 = DATEADD(MM, -@_SaleVelocityNum, DATEFROMPARTS(YEAR(@_DocDate), MONTH(@_DocDate), 1))
	SET @_DocDate0 = DATEFROMPARTS(YEAR(@_DocDate1), 1, 1)
	IF OBJECT_ID(N'Tempdb..#_HoaDon') IS NOT NULL DROP TABLE #_HoaDon
	SELECT TOP 0 CAST('' AS VARCHAR(24)) ItemCode, CAST('' AS NVARCHAR(24)) UnitDMS, CAST(0 AS NUMERIC(16,5)) AvgQuantityDMS, CAST(0 AS INT) MonthNum
	INTO #_HoaDon
	;WITH Sale AS (
		SELECT ct.ItemCode, ct.Unit, ct.Quantity9 Quantity, 'H2' DocCode, DATEFROMPARTS(YEAR(hdr.DocDate), MONTH(hdr.DocDate), 1) MonthSale
		FROM dbo.BRVSX_HoaDonCt ct
			LEFT JOIN dbo.BRVSX_HoaDonHdr hdr ON ct.Stt = hdr.Stt
			INNER JOIN dbo.BRVSX_SanPham sp ON ct.ItemCode = sp.Code AND sp.ItemGroupCode IN ('155','156') AND sp.IsItemWithLot = 1
			INNER JOIN dbo.BRV_TrangThaiHoaDon tt ON tt.EInvoiceStatusKey = hdr.EInvoiceStatus AND ISNULL(tt.IsCancelled, 0) = 0
			INNER JOIN dbo.BRV_TrangThaiDuyet td ON td.DocStatusKey = hdr.DocStatus AND td.Post_TheKho = 1 AND td.IsCancelled = 0
		WHERE hdr.IsActive = 1	AND ct.UnitPrice > 0 AND hdr.DocDate BETWEEN @_DocDate0 AND @_DocDate2
			AND NOT(ISNULL(hdr.DistributorCode,'') = 'KHAC' OR (ISNULL(hdr.DistributorCode,'') = '' AND hdr.Description LIKE N'Xuất hàng%')) AND YEAR(hdr.DocDate) >= 2026
		--AND hdr.CustomerCode NOT IN ('P000001','1000152')
		UNION ALL
		SELECT ct.ItemCode, ct.Unit, IIF(ct.DocGroup = 1, -1, 1) * ct.Quantity9 Quantity, 'HC' DocCode, DATEFROMPARTS(YEAR(ct.DocDate), MONTH(ct.DocDate), 1) MonthSale
		FROM dbo.BRVSX_HoaDonHCCt ct
			INNER JOIN dbo.BRVSX_SanPham sp ON ct.ItemCode = sp.Code AND sp.ItemGroupCode IN ('155','156') AND sp.IsItemWithLot = 1
		WHERE ct.IsActive = 1 AND UnitPrice > 0 AND ct.DocDate BETWEEN @_DocDate0 AND @_DocDate2 AND ISNULL(ct.DistributorCode,'') NOT IN ('','KHAC') AND YEAR(ct.DocDate) >= 2026),
	PastSale AS (
		SELECT ItemCode, DocDate, Unit, Quantity,
			ROW_NUMBER() OVER (PARTITION BY ItemCode ORDER BY DocDate DESC) Seq
		FROM dbo.FACT_SanPhamThang),
	SaleRep AS (
		SELECT ItemCode, DocDate, Unit, Quantity
		FROM PastSale WHERE Seq <= 6
		UNION ALL
		SELECT s.ItemCode, s.MonthSale, sp.UnitDMS,
			SUM(IIF(UPPER(s.Unit) = UPPER(sp.Unit), s.Quantity, dvt.ConvertRate * s.Quantity) / sp.ConvertRateDMS)
		FROM Sale s
			LEFT JOIN dbo.BRVSX_SanPham sp ON sp.Code = s.ItemCode
			LEFT JOIN dbo.BRVSX_SanPhamDvt dvt ON sp.Id = dvt.ItemId AND UPPER(s.Unit) = UPPER(dvt.Unit)
		GROUP BY s.ItemCode, sp.UnitDMS, MonthSale),
	SaleRep1 AS (
		SELECT ItemCode, DocDate, Unit, Quantity,
			ROW_NUMBER() OVER (PARTITION BY ItemCode ORDER BY DocDate DESC) Seq
		FROM SaleRep)
	--SELECT * FROM SaleRep1 WHERE SaleRep1.ItemCode = '71190230060' RETURN
	INSERT INTO #_HoaDon (ItemCode, UnitDMS, AvgQuantityDMS, MonthNum)
	SELECT ItemCode, Unit, UPPER(SUM(Quantity)/COUNT(DISTINCT DocDate)), COUNT(DISTINCT DocDate)
	FROM SaleRep1
	WHERE Seq <= 6
	GROUP BY ItemCode, Unit
	IF Object_Id(N'Tempdb..#OpenInventoryLot') IS NOT NULL DROP TABLE #OpenInventoryLot
	SELECT TOP 0 ItemCode WarehouseCode, ItemCode, CAST('' AS VARCHAR(24)) ItemLotCode, UnitDMS Unit,
		CAST(0 AS NUMERIC(16,5)) AS CloseQuantity, UnitDMS, CAST(0 AS NUMERIC(16,5))  AS CloseQuantityDMS,
		CAST('' AS VARCHAR(24)) ClassCode, CAST(0 AS INT) ItemId
	INTO #OpenInventoryLot
	FROM #_HoaDon
	;WITH OpenStock AS (
		SELECT WarehouseCode, ItemCode, ItemId, Unit, ClassCode, ItemLotCode, SUM(Quantity)	Quantity, SUM(QuantityDMS) QuantityDMS, UnitDMS, 0 StockType
		FROM dbo.vTonKhoDKLot
		WHERE Year = YEAR(@_DocDate)
		GROUP BY WarehouseCode, ItemCode, Unit, ClassCode, ItemLotCode, UnitDMS, ItemId
		HAVING SUM(Quantity) <> 0
		UNION ALL
		SELECT WarehouseCode, ItemCode, ItemId, Unit, ClassCode, ItemLotCode, SUM(ReceiptQuantity - IssueQuantity) Quantity, SUM(ReceiptQuantityDMS - IssueQuantityDMS) QuantityDMS, UnitDMS, 1 StockType
		FROM dbo.vTheKhoLot
		WHERE FiscalYear = YEAR(@_DocDate) AND DocDate <= @_DocDate
		GROUP BY WarehouseCode, ItemCode, Unit, ClassCode, ItemLotCode, UnitDMS, ItemId
		HAVING SUM(ReceiptQuantity - IssueQuantity) <> 0)
	INSERT INTO #OpenInventoryLot (WarehouseCode, ItemCode, Unit, ClassCode, ItemLotCode, CloseQuantity, UnitDMS, CloseQuantityDMS, ItemId)
	SELECT WarehouseCode, ItemCode, Unit, ClassCode, ItemLotCode, SUM(Quantity)	Quantity, UnitDMS, SUM(QuantityDMS), ItemId
	FROM OpenStock
	GROUP BY WarehouseCode, ItemCode, Unit, ClassCode, ItemLotCode, UnitDMS, ItemId
	HAVING SUM(Quantity) <> 0
	IF @_WarehouseCodeNotIncluded <> ''
	BEGIN
		SET @_WarehouseCodeNotIncluded = REPLACE(TRIM(@_WarehouseCodeNotIncluded),' ','')
		DELETE FROM #OpenInventoryLot
		WHERE WarehouseCode IN (
			SELECT value
			FROM STRING_SPLIT(@_WarehouseCodeNotIncluded, ','))
	END
	IF Object_Id(N'Tempdb..#OpenInventory') IS NOT NULL DROP TABLE #OpenInventory
	SELECT ItemCode, Unit, SUM(CloseQuantity) Quantity, SUM(CloseQuantityDMS) QuantityDMS, UnitDMS
	INTO #OpenInventory
	FROM #OpenInventoryLot
	GROUP BY ItemCode, Unit, UnitDMS
	HAVING SUM(CloseQuantity) <> 0
	IF @_RepType = 0
	BEGIN
		;WITH LotCatg AS (
			SELECT ItemLotCode, ItemId, MfgDate, ExpiryDate, 'SX' ClassCode
			FROM dbo.BRVSX_Lot
			WHERE CAST(CreatedAt AS DATE) <= DATEADD(MM, 1, @_DocDate) AND IsActive = 1
			UNION ALL
			SELECT ItemLotCode, ItemId, MfgDate, ExpiryDate, 'TM' ClassCode
			FROM dbo.BRV_Lot
			WHERE CAST(CreatedAt AS DATE) <= DATEADD(MM, 1, @_DocDate) AND IsActive = 1)
		SELECT ROW_NUMBER() OVER (ORDER BY cat.ClassCode, lot.ItemCode, cat.ItemLotCode) Stt,
			lot.ClassCode, lot.WarehouseCode, w.Name WarehouseName,
			lot.ItemCode, i.Name ItemName, i.Unit, i.UnitDMS, lot.CloseQuantity, lot.CloseQuantityDMS,
			lot.ItemLotCode, cat.MfgDate, cat.ExpiryDate, IIF(cat.ExpiryDate > GETDATE(), DATEDIFF(DAY, GETDATE(), cat.ExpiryDate), 0) ExpiryDateDiff,
			CASE WHEN IIF(cat.ExpiryDate > GETDATE(), DATEDIFF(MM, GETDATE(), cat.ExpiryDate), 0) <= 0 THEN lot.CloseQuantity ELSE 0 END CloseQuantity0,
			CASE WHEN IIF(cat.ExpiryDate > GETDATE(), DATEDIFF(MM, GETDATE(), cat.ExpiryDate), 0) BETWEEN 1 AND @_ExpiryPeriod -1 THEN lot.CloseQuantity ELSE 0 END CloseQuantity1,
			CASE WHEN IIF(cat.ExpiryDate > GETDATE(), DATEDIFF(MM, GETDATE(), cat.ExpiryDate), 0) BETWEEN @_ExpiryPeriod AND 2*@_ExpiryPeriod - 1 THEN lot.CloseQuantity ELSE 0 END CloseQuantity2,
			CASE WHEN IIF(cat.ExpiryDate > GETDATE(), DATEDIFF(MM, GETDATE(), cat.ExpiryDate), 0) BETWEEN 2*@_ExpiryPeriod AND 3*@_ExpiryPeriod - 1 THEN lot.CloseQuantity ELSE 0 END CloseQuantity3,
			CASE WHEN IIF(cat.ExpiryDate > GETDATE(), DATEDIFF(MM, GETDATE(), cat.ExpiryDate), 0) BETWEEN 3*@_ExpiryPeriod AND 4*@_ExpiryPeriod - 1 THEN lot.CloseQuantity ELSE 0 END CloseQuantity4,
			CASE WHEN IIF(cat.ExpiryDate > GETDATE(), DATEDIFF(MM, GETDATE(), cat.ExpiryDate), 0) BETWEEN 4*@_ExpiryPeriod AND 6*@_ExpiryPeriod - 1 THEN lot.CloseQuantity ELSE 0 END CloseQuantity5,
			CASE WHEN IIF(cat.ExpiryDate > GETDATE(), DATEDIFF(MM, GETDATE(), cat.ExpiryDate), 0) >= 6*@_ExpiryPeriod THEN lot.CloseQuantity ELSE 0 END CloseQuantity6,
			pa.Name ParentName1, grand.Name ParentName2, IIF(grand.Name IS NOT NULL, grand.Name, pa.Name) ParentName3,
			CASE WHEN IIF(cat.ExpiryDate > GETDATE(), DATEDIFF(DAY, GETDATE(), cat.ExpiryDate), 0) <= @_ExpiryDays THEN N'Hết date'
			WHEN IIF(cat.ExpiryDate > GETDATE(), DATEDIFF(DAY, GETDATE(), cat.ExpiryDate), 0) BETWEEN @_ExpiryDays + 1 AND @_NearExpiryDays - 1 THEN N'Cận date'
			ELSE '' END Description
		FROM #OpenInventoryLot lot
			LEFT JOIN dbo.vKho w ON w.Code = lot.WarehouseCode AND w.ClassCode = lot.ClassCode
			LEFT JOIN dbo.BRVSX_SanPham i ON i.Code = lot.ItemCode
			LEFT JOIN LotCatg cat ON cat.ItemId = lot.ItemId AND cat.ClassCode = lot.ClassCode AND cat.ItemLotCode = lot.ItemLotCode
			LEFT JOIN dbo.BRVSX_SanPham pa ON i.ParentId = pa.Id AND pa.IsGroup = 1
			LEFT JOIN dbo.BRVSX_SanPham grand ON pa.ParentId = grand.Id AND grand.IsGroup = 1
		ORDER BY Stt
	END
	IF @_RepType = 1
	BEGIN
		SELECT i.Code ItemCode, i.Name ItemName, i.Unit, i.UnitDMS, sto.Quantity, sto.QuantityDMS, sale.MonthNum, sale.AvgQuantityDMS,
			FLOOR(sto.QuantityDMS/sale.AvgQuantityDMS) RemainMonths, pa.Name ParentName1, grand.Name ParentName2,
			IIF(grand.Name IS NOT NULL, grand.Name, pa.Name) ParentName3,
			CASE WHEN FLOOR(sto.QuantityDMS/sale.AvgQuantityDMS) <= 1 THEN N'Thiếu hàng'
				WHEN FLOOR(sto.QuantityDMS/sale.AvgQuantityDMS) >= 6 THEN N'Bán chậm'
				ELSE N'Bình thường' END Description,
			CASE WHEN sale.AvgQuantityDMS IS NULL THEN N'Không phát sinh DS' END SaleType
		FROM  dbo.BRVSX_SanPham i
			INNER JOIN #OpenInventory sto ON sto.ItemCode = i.Code AND i.IsItemWithLot = 1 AND i.ItemGroupCode IN ('155','156')
			LEFT JOIN #_HoaDon sale ON sale.ItemCode = sto.ItemCode AND sale.UnitDMS = sto.UnitDMS
			LEFT JOIN dbo.BRVSX_SanPham pa ON i.ParentId = pa.Id AND pa.IsGroup = 1
			LEFT JOIN dbo.BRVSX_SanPham grand ON pa.ParentId = grand.Id AND grand.IsGroup = 1
		ORDER BY i.Code
	END
	IF OBJECT_ID('TempDb..#_CustomerList') IS NOT NULL DROP TABLE #_CustomerList
	IF OBJECT_ID('TempDb..#_HoaDon') IS NOT NULL DROP TABLE #_HoaDon
	IF OBJECT_ID('TempDb..#_HoaDon_Past') IS NOT NULL DROP TABLE #_HoaDon_Past
	IF OBJECT_ID('TempDb..#_HoaDon_Pre') IS NOT NULL DROP TABLE #_HoaDon_Pre
END
