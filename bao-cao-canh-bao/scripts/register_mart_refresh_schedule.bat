@echo off
:: Dang ky Scheduled Task chay scripts/build_mart_revenue_summary.py hang dem luc 2h sang
:: (gio thap diem, Disk IO du thua - theo dung de xuat 08/07/2026) de cap nhat mart_revenue_summary.
:: Mac dinh incremental (7 ngay gan nhat) - RE, khong phai full backfill.
::
:: Dang ky duoi SYSTEM tu dau (khac voi lan dau lam lich Bravo sync sang nay bi loi vi dung
:: Interactive thieu quyen admin luc do) - khong phu thuoc phien dang nhap.
:: CAN CHAY FILE NAY VOI QUYEN ADMINISTRATOR (chuot phai > Run as administrator).

set PYTHON_PATH=C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
set SCRIPT_PATH=D:\DNH\scripts\build_mart_revenue_summary.py

schtasks /create /tn "DNH_Mart_Revenue_Refresh_0200" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\"" /sc daily /st 02:00 /ru SYSTEM /rl HIGHEST /f

echo.
echo ============================================================
echo Da dang ky task DNH_Mart_Revenue_Refresh_0200 (2h sang hang ngay, chay duoi SYSTEM).
echo Kiem tra: schtasks /query /fo LIST /tn "DNH_Mart_Revenue_Refresh_0200"
echo LUU Y: lan dau can chay backfill thu cong 1 lan (--full) khi IO da hoi phuc:
echo   python D:\DNH\scripts\build_mart_revenue_summary.py --full
echo ============================================================
pause
