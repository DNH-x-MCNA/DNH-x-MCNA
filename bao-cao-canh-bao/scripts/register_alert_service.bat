@echo off
:: Di chuyen ve dung thu muc du an
cd /d "D:\DNH"

:: Xoa file log cu neu co
if exist nssm_alert_log.txt del nssm_alert_log.txt

set NSSM_PATH=C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe
set PYTHON_PATH=C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
set PROJECT_DIR=D:\DNH
set SCRIPT_PATH=D:\DNH\main.py
set SERVICE_NAME=DNH_Realtime_Alerts

echo Dang kiem tra va dung Service cu neu dang chay... >> nssm_alert_log.txt
"%NSSM_PATH%" stop %SERVICE_NAME% >> nssm_alert_log.txt 2>&1
net stop %SERVICE_NAME% >> nssm_alert_log.txt 2>&1

:: Cho 3 giay de Windows giai phong hoan toan cac tien trinh
ping 127.0.0.1 -n 4 >nul

echo Dang go cai dat Service cu... >> nssm_alert_log.txt
"%NSSM_PATH%" remove %SERVICE_NAME% confirm >> nssm_alert_log.txt 2>&1

:: Cho them 2 giay de he thong xoa sach registry
ping 127.0.0.1 -n 3 >nul

echo Dang khoi tao Windows Service: %SERVICE_NAME%...
echo Dang chay nssm install... >> nssm_alert_log.txt
"%NSSM_PATH%" install %SERVICE_NAME% "%PYTHON_PATH%" -u "%SCRIPT_PATH%" >> nssm_alert_log.txt 2>&1

echo Dang cau hinh thu muc va file logs... >> nssm_alert_log.txt
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%PROJECT_DIR%" >> nssm_alert_log.txt 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "D:\DNH\alert_service_stdout.log" >> nssm_alert_log.txt 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "D:\DNH\alert_service_stderr.log" >> nssm_alert_log.txt 2>&1

echo Dang cau hinh Description va Start type... >> nssm_alert_log.txt
"%NSSM_PATH%" set %SERVICE_NAME% Description "Dich vu giam sat va phat canh bao nghiep vu tu dong (ERP/CRM) cua Duoc Nam Ha" >> nssm_alert_log.txt 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_AUTO_START >> nssm_alert_log.txt 2>&1

echo Dang khoi dong Service: %SERVICE_NAME%...
net start %SERVICE_NAME%

echo.
echo ============================================================
echo Da cap nhat va khoi dong Windows Service: %SERVICE_NAME%
echo Service se tu chay ngam moi khi may tinh khoi dong.
echo Vui long kiem tra file "D:\DNH\nssm_alert_log.txt" de xem ket qua!
echo ============================================================
pause
