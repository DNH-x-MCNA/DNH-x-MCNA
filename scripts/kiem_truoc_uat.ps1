[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$checks = @(
    @{
        Name = 'Tai khoan va pham vi du lieu'
        Args = @('.\scripts\kiem_tai_khoan_thieu_pham_vi.py', '--db', '.\backend\auth.db')
    },
    @{
        Name = 'Phan quyen kenh ETC'
        Args = @('.\scripts\verify_etc_channel_scope.py')
    },
    @{
        Name = 'Bat bien so lieu cua 40 cong cu'
        Args = @('.\scripts\doi_chieu_so_lieu_tool_moi.py')
    }
)

$results = @()
foreach ($check in $checks) {
    Write-Host ''
    Write-Host ('=' * 78)
    Write-Host ('DANG KIEM: ' + $check.Name)
    Write-Host ('=' * 78)
    & python @($check.Args)
    $results += [pscustomobject]@{
        Name = $check.Name
        Passed = ($LASTEXITCODE -eq 0)
    }
}

Write-Host ''
Write-Host ('=' * 78)
Write-Host 'TONG KET TRUOC UAT'
Write-Host ('=' * 78)
foreach ($result in $results) {
    $label = if ($result.Passed) { '[DAT]' } else { '[CHUA DAT]' }
    Write-Host ("{0} {1}" -f $label, $result.Name)
}

if ($results.Passed -contains $false) {
    Write-Host ''
    Write-Host 'KET LUAN: CHUA NEN giao tai khoan cho tester. Sua cac muc CHUA DAT roi chay lai.'
    exit 1
}

Write-Host ''
Write-Host 'KET LUAN: Cac cong kiem tra tu dong da dat; co the chuyen sang buoc test 5 cau.'
exit 0
