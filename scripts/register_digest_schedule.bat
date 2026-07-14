@echo off
:: Dang ky 3 Scheduled Task gui bao cao Daily/Weekly/Monthly qua Email, thay cho logic so khop
:: phut cu trong vong lap main.py (da bo, xem ghi chu trong config/config.yaml).
:: Dung cac co --send-daily/--send-weekly/--send-monthly co san trong main.py, chi chay 1 lan
:: roi thoat - khong can process thuong truc.
::
:: CHAY DUOI TAI KHOAN SYSTEM (/RU SYSTEM) - khong phu thuoc phien dang nhap tuong tac, dung
:: bai hoc tu viec lam lich Bravo Sync truoc day (Interactive gay mat/le lich khi may khong co
:: phien dang nhap lien tuc).
:: CAN CHAY FILE NAY VOI QUYEN ADMINISTRATOR (chuot phai > Run as administrator).

set PYTHON_PATH=C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
set MAIN_PATH=D:\DNH\main.py

schtasks /create /tn "DNH_Daily_Digest_1745" /tr "\"%PYTHON_PATH%\" \"%MAIN_PATH%\" --send-daily" /sc weekly /d MON,TUE,WED,THU,FRI /st 17:45 /ru SYSTEM /rl HIGHEST /f
schtasks /create /tn "DNH_Weekly_Report" /tr "\"%PYTHON_PATH%\" \"%MAIN_PATH%\" --send-weekly" /sc weekly /d SAT /st 15:00 /ru SYSTEM /rl HIGHEST /f
schtasks /create /tn "DNH_Monthly_Report" /tr "\"%PYTHON_PATH%\" \"%MAIN_PATH%\" --send-monthly" /sc monthly /mo LASTDAY /m * /st 17:45 /ru SYSTEM /rl HIGHEST /f

echo.
echo ============================================================
echo Da dang ky 3 task: DNH_Daily_Digest_1745 (Thu Hai - Thu Sau, 17:45),
echo DNH_Weekly_Report (thu Bay 15:00), DNH_Monthly_Report (ngay cuoi thang 17:45).
echo Kiem tra: schtasks /query /fo LIST /tn "DNH_Daily_Digest_1745"
echo ============================================================
pause
