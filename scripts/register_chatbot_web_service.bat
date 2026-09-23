@echo off
:: ############################################################################
:: ## KHONG CHAY FILE NAY DE RESTART CHATBOT.                                ##
:: ##                                                                        ##
:: ## File nay GO BO (nssm remove) roi CAI LAI service tu dau. Chay nham tren ##
:: ## may 24 dang phuc vu nguoi dung la lam dut dich vu va mat cau hinh hien  ##
:: ## co. Chi dung khi lan DAU dang ky, hoac khi co chu dich cai lai.         ##
:: ##                                                                        ##
:: ## Restart thuong ngay (sau khi git pull) - PowerShell quyen Admin:        ##
:: ##     Restart-Service DNH_Chatbot_Backend -Force                          ##
:: ############################################################################
::
:: THUC TE TREN MAY 24 (do ngay 23/09/2026, dung de doi chieu khi sua bien ben duoi):
::   - Repo clone tai   : C:\dnh_chatbot   (KHONG phai D:\DNH)
::   - Service chatbot  : DNH_Chatbot_Backend   (KHONG phai DNH_Chatbot_Web)
::   - Service canh bao : DNH_Realtime_Alerts   (dang ky boi register_alert_service.bat)
::   - Service tunnel   : DNH_Chatbot_Tunnel    (Cloudflare, KHONG co script dang ky trong repo)
:: Ba service tren doc lap nhau. Va ban code trong backend/ thi chi can restart
:: DNH_Chatbot_Backend; restart nham DNH_Realtime_Alerts la lam gian doan canh bao ma khong
:: giai quyet gi.
::
:: Dang ky Windows Service chay web chatbot (backend/main.py + frontend/) thuong truc qua NSSM.
:: CHAY TREN MAY 24 (khong phai may nay) — sua 4 dong "set ...PATH/DIR" ben duoi cho dung
:: duong dan THAT tren may 24 truoc khi chay (repo clone o dau, Python cai o dau, NSSM cai o dau).
::
:: Dieu kien can co TRUOC khi chay file nay (xem huong dan day du kem theo):
::   1. Da clone repo ve may 24 va tao file .env voi day du bien (xem .env.example).
::   2. Da chay "pip install -r requirements.txt" thanh cong trong thu muc repo.
::   3. Da test thu cong "python backend\main.py" chay duoc, mo trinh duyet vao that thay web.
::   4. Da cai NSSM (hoac dung duong dan NSSM co san neu may 24 da dung NSSM cho service khac).

cd /d "C:\dnh_chatbot"

:: ===== SUA 4 DONG DUOI CHO DUNG MAY 24 =====
set NSSM_PATH=C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe
set PYTHON_PATH=C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
set PROJECT_DIR=C:\dnh_chatbot
set SCRIPT_PATH=C:\dnh_chatbot\backend\main.py
:: ============================================

set SERVICE_NAME=DNH_Chatbot_Backend

echo Dang kiem tra va dung Service cu neu dang chay... >> nssm_chatbot_web_log.txt
"%NSSM_PATH%" stop %SERVICE_NAME% >> nssm_chatbot_web_log.txt 2>&1
net stop %SERVICE_NAME% >> nssm_chatbot_web_log.txt 2>&1

ping 127.0.0.1 -n 4 >nul

echo Dang go cai dat Service cu... >> nssm_chatbot_web_log.txt
"%NSSM_PATH%" remove %SERVICE_NAME% confirm >> nssm_chatbot_web_log.txt 2>&1

ping 127.0.0.1 -n 3 >nul

echo Dang khoi tao Windows Service: %SERVICE_NAME%...
echo Dang chay nssm install... >> nssm_chatbot_web_log.txt
"%NSSM_PATH%" install %SERVICE_NAME% "%PYTHON_PATH%" "%SCRIPT_PATH%" >> nssm_chatbot_web_log.txt 2>&1

echo Dang cau hinh thu muc va file logs... >> nssm_chatbot_web_log.txt
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%PROJECT_DIR%" >> nssm_chatbot_web_log.txt 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%PROJECT_DIR%\chatbot_web_stdout.log" >> nssm_chatbot_web_log.txt 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "%PROJECT_DIR%\chatbot_web_stderr.log" >> nssm_chatbot_web_log.txt 2>&1

echo Dang cau hinh Description va Start type... >> nssm_chatbot_web_log.txt
"%NSSM_PATH%" set %SERVICE_NAME% Description "Web Chatbot AI (backend/main.py + frontend) cua Duoc Nam Ha" >> nssm_chatbot_web_log.txt 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_AUTO_START >> nssm_chatbot_web_log.txt 2>&1

echo Dang khoi dong Service: %SERVICE_NAME%...
net start %SERVICE_NAME%

echo.
echo ============================================================
echo Da cap nhat va khoi dong Windows Service: %SERVICE_NAME%
echo Service se tu chay ngam moi khi may tinh khoi dong.
echo Truy cap tu chinh may 24: http://127.0.0.1:8000 (hoac dung BACKEND_PORT trong .env neu doi)
echo Truy cap tu may khac trong LAN: http://<IP-may-24>:8000
echo Vui long kiem tra file "%PROJECT_DIR%\nssm_chatbot_web_log.txt" de xem ket qua!
echo ============================================================
pause
