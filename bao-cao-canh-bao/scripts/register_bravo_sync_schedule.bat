@echo off
:: Dang ky 5 Scheduled Task de tu dong chay sync_from_bravo_to_supabase.py hang ngay
:: luc 9h, 12h, 15h, 18h, 21h (kéo dữ liệu thật từ SQL Server DNH sang Supabase dev).
:: Khac voi DNH_Realtime_Alerts/DNH_Supabase_Sync (NSSM service chay lien tuc), day la
:: Task Scheduler thong thuong vi chi can chay tai 5 moc gio co dinh roi thoat, khong
:: can mot process thuong truc.
::
:: CHAY DUOI TAI KHOAN SYSTEM (/RU SYSTEM) - khong phu thuoc phien dang nhap tuong tac.
:: Ban dau dang ky kieu "Interactive" (thieu quyen admin luc do) da gay loi thuc te ngay
:: 07/07/2026: task 09h/12h khong chay, 15h/18h bi don chay sai gio luc 21h02, va task 21h
:: bi kill giua chung - deu do phien dang nhap khong lien tuc. /RU SYSTEM sua tan goc.
:: CAN CHAY FILE NAY VOI QUYEN ADMINISTRATOR (chuot phai > Run as administrator).

set PYTHON_PATH=C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
set SCRIPT_PATH=D:\DNH\scripts\sync_from_bravo_to_supabase.py

schtasks /create /tn "DNH_Bravo_Sync_0900" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\"" /sc daily /st 09:00 /ru SYSTEM /rl HIGHEST /f
schtasks /create /tn "DNH_Bravo_Sync_1200" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\"" /sc daily /st 12:00 /ru SYSTEM /rl HIGHEST /f
schtasks /create /tn "DNH_Bravo_Sync_1500" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\"" /sc daily /st 15:00 /ru SYSTEM /rl HIGHEST /f
schtasks /create /tn "DNH_Bravo_Sync_1800" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\"" /sc daily /st 18:00 /ru SYSTEM /rl HIGHEST /f
schtasks /create /tn "DNH_Bravo_Sync_2100" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\"" /sc daily /st 21:00 /ru SYSTEM /rl HIGHEST /f

echo.
echo ============================================================
echo Da dang ky lai 5 scheduled task DNH_Bravo_Sync (9h/12h/15h/18h/21h) chay duoi SYSTEM.
echo Kiem tra: schtasks /query /fo LIST /tn "DNH_Bravo_Sync_0900"
echo ============================================================
pause
