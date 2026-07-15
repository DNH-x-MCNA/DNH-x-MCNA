@echo off
:: Di chuyen ve dung thu muc du an
cd /d "D:\DNH"

:: Xoa file log cu neu co
if exist nssm_log.txt del nssm_log.txt

set NSSM_PATH=C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe
set PYTHON_PATH=C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe
set PROJECT_DIR=D:\DNH
set SCRIPT_PATH=D:\DNH\scripts\sync_daemon.py
set SERVICE_NAME=DNH_Supabase_Sync

echo Dang kiem tra va dung Service cu neu dang chay... >> nssm_log.txt
"%NSSM_PATH%" stop %SERVICE_NAME% >> nssm_log.txt 2>&1
net stop %SERVICE_NAME% >> nssm_log.txt 2>&1

:: Cho 3 giay de Windows giai phong hoan toan cac tien trinh lien quan
ping 127.0.0.1 -n 4 >nul

echo Dang go cai dat Service cu... >> nssm_log.txt
"%NSSM_PATH%" remove %SERVICE_NAME% confirm >> nssm_log.txt 2>&1

:: Cho them 2 giay de he thong xoa sach hoan toan service khoi registry
ping 127.0.0.1 -n 3 >nul

echo Dang khoi tao Windows Service: %SERVICE_NAME%...
echo Dang chay nssm install... >> nssm_log.txt
"%NSSM_PATH%" install %SERVICE_NAME% "%PYTHON_PATH%" -u "%SCRIPT_PATH%" >> nssm_log.txt 2>&1

echo Dang cau hinh thu muc va file logs... >> nssm_log.txt
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%PROJECT_DIR%" >> nssm_log.txt 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "D:\DNH\sync_service_stdout.log" >> nssm_log.txt 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "D:\DNH\sync_service_stderr.log" >> nssm_log.txt 2>&1

echo Dang cau hinh Description va Start type... >> nssm_log.txt
"%NSSM_PATH%" set %SERVICE_NAME% Description "Dich vu dong bo du lieu realtime tu Bravo SQL Server len Supabase Cloud" >> nssm_log.txt 2>&1
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_AUTO_START >> nssm_log.txt 2>&1

echo.
echo ============================================================
echo Da cap nhat cau hinh Service va file logs.
echo Vui long mo file "D:\DNH\nssm_log.txt" de xem ket qua chi tiet!
echo ============================================================
pause
