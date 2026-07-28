@echo off
:: Dang ky Windows Service chay web chatbot (backend/main.py + frontend/) thuong truc qua NSSM.
:: CHAY TREN MAY 24 (khong phai may nay) — sua 4 dong "set ...PATH/DIR" ben duoi cho dung
:: duong dan THAT tren may 24 truoc khi chay (repo clone o dau, Python cai o dau, NSSM cai o dau).
::
:: Dieu kien can co TRUOC khi chay file nay (xem huong dan day du kem theo):
::   1. Da clone repo ve may 24 va tao file .env voi day du bien (xem .env.example).
::   2. Da chay "pip install -r requirements.txt" thanh cong trong thu muc repo.
::   3. Da test thu cong "python backend\main.py" chay duoc, mo trinh duyet vao that thay web.
::   4. Da cai NSSM (hoac dung duong dan NSSM co san neu may 24 da dung NSSM cho service khac).

cd /d "D:\DNH"

:: ===== SUA 4 DONG DUOI CHO DUNG MAY 24 =====
set NSSM_PATH=C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe
set PYTHON_PATH=C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
set PROJECT_DIR=D:\DNH
set SCRIPT_PATH=D:\DNH\backend\main.py
:: ============================================

set SERVICE_NAME=DNH_Chatbot_Web

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
