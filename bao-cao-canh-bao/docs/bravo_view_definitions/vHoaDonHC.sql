
CREATE VIEW [dbo].[vHoaDonHC]
AS
	WITH NVBH AS 
		(SELECT nv.DMSId EmpDMSCode, MAX(ql.DMSId) EmpDMSCode2
		FROM dbo.DIM_NhanVien nv
			LEFT JOIN dbo.DIM_DiaBan db ON nv.ManagerAreaCode = db.Code AND db.IsActive = 1
			LEFT JOIN dbo.DIM_NhanVien ql ON ql.EmployeeCode = db.ManagerCode
		GROUP BY nv.DMSId)
	SELECT ct.BranchCode, ct.DistributorCode, ct.Id, ct.RowId, ct.ItemCode, ct.Unit, ct.DocGroup, IIF(ct.DocGroup = 1, -1, 1) * ct.Quantity9 Quantity, ct.UnitPrice, 
		IIF(ct.DocGroup = 1, -1, 1) * ct.Amount9 Amount9,
		ct.TaxCode, ct.TaxRate, IIF(ct.DocGroup = 1, -1, 1) * ct.Amount3 Amount3, 
		ct.DiscountRate, IIF(ct.DocGroup = 1, -1, 1) * ct.Amount4 Amount4, IIF(ct.DocGroup = 1, -1, 1) * ct.Reduce Reduce, ct.CTKM,
		ct.CreatedAt, ct.ModifiedAt, ct.SyncAt, 
		ct.DocDate, 
		ct.EmpDMSCode EmpDMSCode, 
		ct.EmpDMSCode2, 
		CASE WHEN ct.CustomerCode = 'NDI10105' THEN TRIM(ct.Description)
			WHEN ct.CustomerCode IN ('HCM04272','HCM14237') THEN 'HCM04272'
			WHEN ct.CustomerCode IN ('HCM04298','HCM14236') THEN 'HCM04298'			
			WHEN ct.CustomerCode IN ('HNO03986','HNO11477') THEN 'HNO03986'
			WHEN ct.CustomerCode IN ('HCM14365','HCM14366') THEN 'HCM14365'
			ELSE ct.CustomerCode END CustomerCode, 
		ct.Stt,
		sp.GroupCode, 'HC' DocCode, ct.DMSId, 
		ISNULL(kh.EmpDMSCode1, ct.EmpDMSCode) CurEmpDMSCode, ISNULL(ql.EmpDMSCode2, ct.EmpDMSCode2) CurEmpDMSCode2,
		ct.CustomerCode CustomerCode0, ct.DocNo, kh.Id CusDMSSeq, kh.CityId, kh.DistrictId, kh.StreetId
	FROM dbo.BRV_HoaDonHCCt ct
		LEFT JOIN dbo.DIM_NhomSanPham sp ON sp.ItemCode = ct.ItemCode
		LEFT JOIN dbo.DMS_KhachHang kh ON IIF(ct.CustomerCode = 'NDI10105',TRIM(ct.Description), ct.CustomerCode) = kh.Code
		LEFT JOIN NVBH ql ON ql.EmpDMSCode = kh.EmpDMSCode1
		INNER JOIN dbo.BRV_TrangThaiDuyet td ON td.DocStatusKey = ct.DocStatus AND td.Post_TheKho = 1 AND td.IsCancelled = 0
	WHERE (ISNULL(ct.Amount9, 0) > 0) AND ct.IsActive = 1
	UNION ALL 
	SELECT ct.BranchCode, ct.DistributorCode, ct.Id, ct.RowId, ct.ItemCode, ct.Unit, ct.DocGroup, IIF(ct.DocGroup = 1, -1, 1) * ct.Quantity Quantity, ct.UnitPrice, 
		IIF(ct.DocGroup = 1, -1, 1) * ct.Amount9 Amount9,
		ct.TaxCode, ct.TaxRate, IIF(ct.DocGroup = 1, -1, 1) * ct.Amount3 Amount3, 
		ct.DiscountRate, IIF(ct.DocGroup = 1, -1, 1) * ct.Amount4 Amount4, IIF(ct.DocGroup = 1, -1, 1) * ct.Reduce Reduce, ct.CTKM,
		ct.CreatedAt, ct.ModifiedAt, ct.SyncAt, 
		ct.DocDate, 
		IIF(ct.CustomerCode = 'HDU00632', 'DNH00649', kh.EmpDMSCode1) EmpDMSCode, 
		IIF(ct.CustomerCode = 'HDU00632', 'ASM12', ql.EmpDMSCode2) EmpDMSCode2, 
		CASE WHEN ct.CustomerCode = 'NDI10105' THEN TRIM(ct.Description)
			WHEN ct.CustomerCode IN ('HCM04272','HCM04272') THEN 'HCM04272'
			WHEN ct.CustomerCode IN ('HCM04298','HCM14236') THEN 'HCM04298'			
			WHEN ct.CustomerCode IN ('HNO03986','HNO11477') THEN 'HNO03986'
			WHEN ct.CustomerCode IN ('HCM14365','HCM14366') THEN 'HCM14365'
			ELSE ct.CustomerCode END CustomerCode, 
		ct.Stt,
		sp.GroupCode, 'HC' DocCode, ct.DMSId, 
		IIF(ct.CustomerCode = 'HDU00632', 'DNH00649', kh.EmpDMSCode1) CurEmpDMSCode, IIF(ct.CustomerCode = 'HDU00632', 'ASM12', ql.EmpDMSCode2) CurEmpDMSCode2,
		ct.CustomerCode CustomerCode0, ct.DocNo, kh.Id CusDMSSeq, kh.CityId, kh.DistrictId, kh.StreetId
	FROM dbo.BRVSX_HoaDonHCCt ct
		LEFT JOIN dbo.DIM_NhomSanPham sp ON sp.ItemCode = ct.ItemCode
		LEFT JOIN dbo.DMS_KhachHang kh ON IIF(ct.CustomerCode = 'NDI10105',TRIM(ct.Description), ct.CustomerCode) = kh.Code
		LEFT JOIN NVBH ql ON ql.EmpDMSCode = kh.EmpDMSCode1
		INNER JOIN dbo.BRV_TrangThaiDuyet td ON td.DocStatusKey = ct.DocStatus AND td.Post_TheKho = 1  AND td.IsCancelled = 0
	WHERE (ISNULL(ct.Amount9, 0) > 0) AND ct.IsActive = 1 AND ct.CustomerCode IN ('HNO02435','HDU00632') AND YEAR(ct.DocDate) >= 2025
	UNION ALL 
	SELECT ct.BranchCode, ct.DistributorCode, ct.Id, ct.RowId, ct.ItemCode, ct.Unit, ct.DocGroup, IIF(ct.DocGroup = 1, -1, 1) * ct.Quantity Quantity, ct.UnitPrice, 
		IIF(ct.DocGroup = 1, -1, 1) * ct.Amount9 Amount9,
		ct.TaxCode, ct.TaxRate, IIF(ct.DocGroup = 1, -1, 1) * ct.Amount3 Amount3, 
		ct.DiscountRate, IIF(ct.DocGroup = 1, -1, 1) * ct.Amount4 Amount4, IIF(ct.DocGroup = 1, -1, 1) * ct.Reduce Reduce, ct.CTKM,
		ct.CreatedAt, ct.ModifiedAt, ct.SyncAt, 
		ct.DocDate, 
		IIF(ct.CustomerCode = 'HDU00632', 'DNH00649', kh.EmpDMSCode1) EmpDMSCode, 
		IIF(ct.CustomerCode = 'HDU00632', 'ASM12', ql.EmpDMSCode2) EmpDMSCode2, 
		CASE WHEN ct.CustomerCode = 'NDI10105' THEN TRIM(ct.Description)
			WHEN ct.CustomerCode IN ('HCM04272','HCM04272') THEN 'HCM04272'
			WHEN ct.CustomerCode IN ('HCM04298','HCM14236') THEN 'HCM04298'			
			WHEN ct.CustomerCode IN ('HNO03986','HNO11477') THEN 'HNO03986'
			WHEN ct.CustomerCode IN ('HCM14365','HCM14366') THEN 'HCM14365'
			ELSE ct.CustomerCode END CustomerCode, 
		ct.Stt,
		sp.GroupCode, 'HC' DocCode, ct.DMSId, 
		IIF(ct.CustomerCode = 'HDU00632', 'DNH00649', kh.EmpDMSCode1) CurEmpDMSCode, IIF(ct.CustomerCode = 'HDU00632', 'ASM12', ql.EmpDMSCode2) CurEmpDMSCode2,
		ct.CustomerCode CustomerCode0, ct.DocNo, kh.Id CusDMSSeq, kh.CityId, kh.DistrictId, kh.StreetId
	FROM dbo.BRVSX_HoaDonHCCt ct
		LEFT JOIN dbo.DIM_NhomSanPham sp ON sp.ItemCode = ct.ItemCode
		LEFT JOIN dbo.DMS_KhachHang kh ON IIF(ct.CustomerCode = 'NDI10105',TRIM(ct.Description), ct.CustomerCode) = kh.Code
		LEFT JOIN NVBH ql ON ql.EmpDMSCode = kh.EmpDMSCode1
		INNER JOIN dbo.BRV_TrangThaiDuyet td ON td.DocStatusKey = ct.DocStatus AND td.Post_TheKho = 1  AND td.IsCancelled = 0
	WHERE (ISNULL(ct.Amount9, 0) > 0) AND ct.IsActive = 1 AND YEAR(ct.DocDate) < 2025
