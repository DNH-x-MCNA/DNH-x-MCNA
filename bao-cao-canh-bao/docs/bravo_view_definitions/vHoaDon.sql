

CREATE VIEW [dbo].[vHoaDon] 
AS
	WITH NVBH AS 
		(SELECT nv.DMSId EmpDMSCode, MAX(ql.DMSId) EmpDMSCode2
		FROM dbo.DIM_NhanVien nv
			LEFT JOIN dbo.DIM_DiaBan db ON nv.ManagerAreaCode = db.Code AND db.IsActive = 1
			LEFT JOIN dbo.DIM_NhanVien ql ON ql.EmployeeCode = db.ManagerCode
		GROUP BY nv.DMSId)
	SELECT hdr.BranchCode, hdr.DistributorCode, ct.Id, ct.RowId, ct.ItemCode, ct.Unit, ct.Quantity9 AS Quantity, ct.UnitPrice, ct.Amount9,
		ct.TaxCode, ct.TaxRate, ct.Amount3, ct.DiscountRate, ct.Amount4, ct.Reduce, ct.CTKM,
		ct.CreatedAt, ct.ModifiedAt, ct.SyncAt, 
		hdr.DocDate, 
		hdr.EmpDMSCode EmpDMSCode, 
		hdr.EmpDMSCode2, 
		CASE WHEN hdr.CustomerCode = 'NDI10105' THEN TRIM(hdr.Description)
			WHEN hdr.CustomerCode IN ('HCM04272','HCM14237') THEN 'HCM04272'
			WHEN hdr.CustomerCode IN ('HCM04298','HCM14236') THEN 'HCM04298'
			WHEN hdr.CustomerCode IN ('HNO03986','HNO11477') THEN 'HNO03986'
			WHEN hdr.CustomerCode IN ('HNO03986','HNO11477') THEN 'HNO03986'
			WHEN hdr.CustomerCode IN ('HCM14365','HCM14366') THEN 'HCM14365'
			ELSE hdr.CustomerCode END CustomerCode, 
		hdr.Stt,
		sp.GroupCode, 'H2' DocCode, hdr.DocNo, hdr.DMSId, 
		ISNULL(kh.EmpDMSCode1, hdr.EmpDMSCode) CurEmpDMSCode, ISNULL(ql.EmpDMSCode2, hdr.EmpDMSCode2) CurEmpDMSCode2,
		hdr.CustomerCode CustomerCode0, kh.Id CusDMSSeq, kh.CityId, kh.DistrictId, kh.StreetId
	FROM dbo.BRV_HoaDonCt ct
		LEFT JOIN dbo.BRV_HoaDonHdr hdr ON ct.Stt = hdr.Stt
		LEFT JOIN dbo.DIM_NhomSanPham sp ON sp.ItemCode = ct.ItemCode
		LEFT JOIN dbo.DMS_KhachHang kh ON IIF(hdr.CustomerCode = 'NDI10105',TRIM(hdr.Description), hdr.CustomerCode) = kh.Code
		LEFT JOIN NVBH ql ON ql.EmpDMSCode = kh.EmpDMSCode1
		INNER JOIN dbo.BRV_TrangThaiHoaDon tt ON tt.EInvoiceStatusKey = hdr.EInvoiceStatus AND ISNULL(tt.IsCancelled, 0) = 0
		INNER JOIN dbo.BRV_TrangThaiDuyet td ON td.DocStatusKey = hdr.DocStatus AND td.Post_TheKho = 1 AND td.IsCancelled = 0
	WHERE hdr.IsActive = 1  AND hdr.EmpDMSCode NOT IN ('SA_CNCT','TM23110137') AND hdr.DistributorCode LIKE 'OTC%' AND hdr.CustomerCode NOT LIKE '%P0000%'
	UNION ALL
    SELECT hdr.BranchCode, hdr.DistributorCode, ct.Id, ct.RowId, ct.ItemCode, ct.Unit, ct.Quantity9, ct.UnitCost, ct.Amount9,
		ct.TaxCode, ct.TaxRate, ct.Amount3,	ct.DiscountRate, IIF(ct.ItemCode <> 'DV000000007',ct.OriginalAmount4,0), IIF(ct.ItemCode = 'DV000000007',ct.OriginalAmount4,0) Reduce, ISNULL(ct.Remark,''),
		ct.CreatedAt, ct.ModifiedAt, ct.SyncAt, 
		hdr.DocDate, hdr.EmpDMSCode, hdr.EmpDMSCode2, hdr.CustomerCode, hdr.BizDocId,
		sp.GroupCode, 'SO' DocCode, hdr.DocNo, hdr.DMSId, 
		ISNULL(kh.EmpDMSCode1, hdr.EmpDMSCode) CurEmpDMSCode, ISNULL(ql.EmpDMSCode2, hdr.EmpDMSCode2) CurEmpDMSCode2,
		hdr.CustomerCode CustomerCode0, kh.Id CusDMSSeq, kh.CityId, kh.DistrictId, kh.StreetId
	FROM dbo.BRV_DonHangCt ct
		LEFT JOIN dbo.BRV_DonHang hdr ON ct.BizDocId = hdr.BizDocId
		LEFT JOIN dbo.DMS_KhachHang kh ON hdr.CustomerCode = kh.Code
		LEFT JOIN dbo.DIM_NhomSanPham sp ON sp.ItemCode = ct.ItemCode
		LEFT JOIN NVBH ql ON ql.EmpDMSCode = kh.EmpDMSCode1
		INNER JOIN dbo.BRV_TrangThaiDuyet td ON td.DocStatusKey = hdr.DocStatus AND td.IsCancelled = 0
	WHERE hdr.IsActive = 1 AND WarehouseCode IN ('WPD05', 'WPD06') --(ISNULL(ct.Amount9, 0) <> 0) AND 
	UNION ALL 
	SELECT hdr.BranchCode, hdr.DistributorCode, ct.Id, ct.RowId, ct.ItemCode, ct.Unit, ct.Quantity9, ct.UnitPrice, ct.Amount9,
		ct.TaxCode, ct.TaxRate, ct.Amount3, ct.DiscountRate, ct.Amount4, ct.Reduce, ct.CTKM,
		ct.CreatedAt, ct.ModifiedAt, ct.SyncAt, 
		hdr.DocDate, 
		IIF(hdr.CustomerCode = 'HDU00632', 'DNH00649', kh.EmpDMSCode1) EmpDMSCode, 
		IIF(hdr.CustomerCode = 'HDU00632', 'ASM12', ql.EmpDMSCode2) EmpDMSCode2, 
		hdr.CustomerCode, 
		hdr.Stt,
		sp.GroupCode, 'H2' DocCode, hdr.DocNo, hdr.DMSId, 
		IIF(hdr.CustomerCode = 'HDU00632', 'DNH00649', kh.EmpDMSCode1) CurEmpDMSCode, IIF(hdr.CustomerCode = 'HDU00632', 'ASM12', ql.EmpDMSCode2) CurEmpDMSCode2,
		hdr.CustomerCode CustomerCode0, kh.Id CusDMSSeq, kh.CityId, kh.DistrictId, kh.StreetId
	FROM dbo.BRVSX_HoaDonCt ct
		LEFT JOIN dbo.BRVSX_HoaDonHdr hdr ON ct.Stt = hdr.Stt
		LEFT JOIN dbo.DIM_NhomSanPham sp ON sp.ItemCode = ct.ItemCode
		LEFT JOIN dbo.DMS_KhachHang kh ON hdr.CustomerCode = kh.Code
		LEFT JOIN NVBH ql ON ql.EmpDMSCode = kh.EmpDMSCode1
		INNER JOIN dbo.BRV_TrangThaiHoaDon tt ON tt.EInvoiceStatusKey = hdr.EInvoiceStatus AND ISNULL(tt.IsCancelled, 0) = 0
		INNER JOIN dbo.BRV_TrangThaiDuyet td ON td.DocStatusKey = hdr.DocStatus AND td.Post_TheKho = 1 AND td.IsCancelled = 0
	WHERE hdr.IsActive = 1 AND hdr.CustomerCode IN ('HNO02435','HDU00632')	AND YEAR(hdr.DocDate) >= 2025
	UNION ALL 
	SELECT hdr.BranchCode, hdr.DistributorCode, ct.Id, ct.RowId, ct.ItemCode, ct.Unit, ct.Quantity9, ct.UnitPrice, ct.Amount9,
		ct.TaxCode, ct.TaxRate, ct.Amount3, ct.DiscountRate, ct.Amount4, ct.Reduce, ct.CTKM,
		ct.CreatedAt, ct.ModifiedAt, ct.SyncAt, 
		hdr.DocDate, 
		kh.EmpDMSCode1 EmpDMSCode, 
		ql.EmpDMSCode2 EmpDMSCode2, 
		hdr.CustomerCode, 
		hdr.Stt,
		sp.GroupCode, 'H2' DocCode, hdr.DocNo, hdr.DMSId, 
		kh.EmpDMSCode1 CurEmpDMSCode, ql.EmpDMSCode2 CurEmpDMSCode2,
		hdr.CustomerCode CustomerCode0, kh.Id CusDMSSeq, kh.CityId, kh.DistrictId, kh.StreetId
	FROM dbo.BRVSX_HoaDonCt ct
		LEFT JOIN dbo.BRVSX_HoaDonHdr hdr ON ct.Stt = hdr.Stt
		LEFT JOIN dbo.DIM_NhomSanPham sp ON sp.ItemCode = ct.ItemCode
		LEFT JOIN dbo.DMS_KhachHang kh ON hdr.CustomerCode = kh.Code
		LEFT JOIN NVBH ql ON ql.EmpDMSCode = kh.EmpDMSCode1
		INNER JOIN dbo.BRV_TrangThaiHoaDon tt ON tt.EInvoiceStatusKey = hdr.EInvoiceStatus AND ISNULL(tt.IsCancelled, 0) = 0
		INNER JOIN dbo.BRV_TrangThaiDuyet td ON td.DocStatusKey = hdr.DocStatus AND td.Post_TheKho = 1 AND td.IsCancelled = 0
	WHERE hdr.IsActive = 1	AND YEAR(hdr.DocDate) < 2025 AND hdr.DistributorCode LIKE 'OTC%' AND (hdr.CustomerCode NOT IN ('1001136','KH999999') AND hdr.CustomerCode NOT LIKE 'P0000%')
	UNION ALL
	SELECT hdr.BranchCode, hdr.DistributorCode, ct.Id, ct.RowId, ct.ItemCode, ct.Unit, ct.Quantity9, ct.UnitPrice, ct.Amount9,
		ct.TaxCode, ct.TaxRate, ct.Amount3, ct.DiscountRate, ct.Amount4, ct.Reduce, ct.CTKM,
		ct.CreatedAt, ct.ModifiedAt, ct.SyncAt, 
		hdr.DocDate, 
		CASE hdr.CustomerCode WHEN 'HCM13508' THEN 'HCM03'
			WHEN 'HDU00632' THEN 'DNH00649' 
			ELSE kh.EmpDMSCode1 END EmpDMSCode, 
		CASE hdr.CustomerCode WHEN 'HCM13508' THEN 'ASM01'
			WHEN 'HDU00632' THEN 'ASM12'
			ELSE ql.EmpDMSCode2 END EmpDMSCode2, 
		hdr.CustomerCode, 
		hdr.Stt,
		sp.GroupCode, 'H2' DocCode, hdr.DocNo, hdr.DMSId, 
		CASE hdr.CustomerCode WHEN 'HCM13508' THEN 'HCM03'
			WHEN 'HDU00632' THEN 'DNH00649' 
			ELSE kh.EmpDMSCode1 END CurEmpDMSCode, 
		CASE hdr.CustomerCode WHEN 'HCM13508' THEN 'ASM01'
			WHEN 'HDU00632' THEN 'ASM12'
			ELSE ql.EmpDMSCode2 END CurEmpDMSCode2,
		hdr.CustomerCode CustomerCode0, kh.Id CusDMSSeq, kh.CityId, kh.DistrictId, kh.StreetId
	FROM dbo.BRVSX_HoaDonCt ct
		LEFT JOIN dbo.BRVSX_HoaDonHdr hdr ON ct.Stt = hdr.Stt
		LEFT JOIN dbo.DIM_NhomSanPham sp ON sp.ItemCode = ct.ItemCode
		LEFT JOIN dbo.DMS_KhachHang kh ON hdr.CustomerCode = kh.Code
		LEFT JOIN NVBH ql ON ql.EmpDMSCode = kh.EmpDMSCode1
		INNER JOIN dbo.BRV_TrangThaiHoaDon tt ON tt.EInvoiceStatusKey = hdr.EInvoiceStatus AND ISNULL(tt.IsCancelled, 0) = 0
		INNER JOIN dbo.BRV_TrangThaiDuyet td ON td.DocStatusKey = hdr.DocStatus AND td.Post_TheKho = 1 AND td.IsCancelled = 0
	WHERE hdr.IsActive = 1 AND hdr.DistributorCode = 'KHAC' AND ct.ItemCode LIKE '811%' AND (hdr.CustomerCode NOT IN ('HCM03814','HCM04325') AND hdr.CustomerCode LIKE 'HCM%') AND hdr.Description NOT LIKE N'%không thu tiền%'
