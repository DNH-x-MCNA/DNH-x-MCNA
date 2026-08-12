@echo off
:: 11/08/2026: Dang ky Task Scheduler chay backend/health_watchdog.py moi 15 phut - phat hien SOM
:: 2 loai su co ha tang tung xay ra AM THAM (khong ai biet cho toi khi tinh co debug viec khac):
:: (1) sync_scheduler.ps1 chet -> warehouse.db dung im hang gio/ngay ma chatbot van tra loi binh
::     thuong (dung du lieu cu, khong bao loi gi ca).
:: (2) cloudflared tunnel doi URL nhung buoc tu dong cap nhat Vercel bi loi -> chatbot production
::     "chet" (frontend goi URL cu da mat) ma khong ai biet cho toi khi nguoi dung bao loi.
:: Phat hien thi gui canh bao qua Teams webhook C-Level co san (dung chung ha tang voi canh bao
:: cong no) - xem health_watchdog.py de biet chi tiet nguong/logic.
::
:: DOC LAP hoan toan voi sync_scheduler.ps1/cloudflared_supervisor.ps1/run_supervisor.ps1 dang
:: chay that - CHI DOC file/log, KHONG sua/khoi dong lai gi ca, nen an toan chay song song ma
:: khong anh huong he thong dang hoat dong.
::
:: CHAY DUOI TAI KHOAN SYSTEM (/RU SYSTEM), giong cac task dinh ky khac trong thu muc nay.
:: CAN CHAY FILE NAY VOI QUYEN ADMINISTRATOR (chuot phai > Run as administrator).

set PYTHON_PATH=C:\Program Files\Python312\python.exe
set SCRIPT_PATH=%~dp0..\backend\health_watchdog.py

schtasks /create /tn "DNH_Chatbot_Health_Watchdog" /tr "\"%PYTHON_PATH%\" \"%SCRIPT_PATH%\"" /sc minute /mo 15 /ru SYSTEM /rl HIGHEST /f

echo.
echo ============================================================
echo Da dang ky task: DNH_Chatbot_Health_Watchdog (chay moi 15 phut).
echo Kiem tra: schtasks /query /fo LIST /tn "DNH_Chatbot_Health_Watchdog"
echo Chay thu ngay: schtasks /run /tn "DNH_Chatbot_Health_Watchdog"
echo ============================================================
pause
