# === Giam sat & tu khoi dong lai: Backend + Sync Scheduler ===
# (May chu DNH - ket noi Bravo TRUC TIEP, khong qua VPN)
# 23/07/2026: BO HAN Telegram Bot khoi bundle nay - kenh chat da chuyen han sang web (dnh-bot.vercel.app),
# Telegram khong con dung. Day cung la nguon sinh tien trinh mo coi: moi lan supervisor nay tu khoi dong
# lai (reboot/restart thu cong) se spawn 1 the he telegram_bot.py MOI ma KHONG kill the he cu (bien
# $botProc chi ton tai trong phien PowerShell hien tai, tien trinh con cu bi "mo coi" khi cha restart) -
# phat hien thuc te 23/07/2026: 4 tien trinh telegram_bot.py song song, tao ngay 16/07, 20/07, 21/07,
# 22/07, khong cai nao chet. Xem docs/kich_ban_demo1_chatbot.md (repo D:\DNH) va memory
# may24_orphan_process_duplication cho boi canh day du ve lop loi nay.
#
# 11/08/2026: GO HAN viec tu spawn Cloudflared Supervisor khoi day (truoc kia co Start-CloudflaredSupervisor
# o day). Ly do: service NSSM "DNH_Chatbot_Backend" (chay script nay) dung tai khoan LocalSystem - tai
# khoan may, KHONG co ho so nguoi dung nen KHONG co dang nhap "npx vercel". Moi lan Restart-Service
# DNH_Chatbot_Backend, ban cloudflared con cua CHINH script nay se giet tunnel dang chay tot (do service
# rieng "DNH_Chatbot_Tunnel", chay duoi .\Administrator, co dang nhap Vercel that) roi tu dung mot tunnel
# MOI - nhung tu cap nhat Vercel that bai ("npx vercel CHUA dang nhap tren may nay"), de lai file
# CAN_SUA_VERCEL.txt va URL cu chet, gay loi HTTP 530 tren toan bo chatbot production cho toi khi co
# nguoi sua tay. Xay ra 2 lan lien tiep ngay 11/08 (14:49 va 15:15), moi lan deu do RESTART BACKEND -
# mot thao tac tuong doi thuong xuyen (deploy code moi) - vo tinh lam sap tunnel.
# Tu nay: quan ly tunnel CHI con 1 noi duy nhat - service NSSM "DNH_Chatbot_Tunnel" (da cai + kiem chung
# 10/08/2026, tu phuc hoi dung sau reboot, dung dung tai khoan co quyen cap nhat Vercel). Script nay
# CHI con phu trach Backend (uvicorn) + Sync Scheduler, khong dong toi cloudflared nua.
$BACKEND_DIR = "C:\dnh_chatbot\backend"
$LOG_DIR = "$BACKEND_DIR\logs"
$SUPERVISOR_LOG = "$LOG_DIR\supervisor.log"
$CHECK_INTERVAL_SEC = 30

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

# Chi cho phep DUNG MOT supervisor tren toan may. Task Scheduler/service/lenh tay co the vo tinh
# khoi dong cung script nhieu lan; moi ban se sinh mot sync_scheduler rieng va tranh nhau ghi
# warehouse.db. Named mutex duoc Windows tu dong giai phong khi process chet, ke ca Stop-Process.
$SUPERVISOR_MUTEX_NAME = "Global\DNH_Chatbot_RunSupervisor"
$ownsSupervisorMutex = $false
try {
    $supervisorMutex = New-Object System.Threading.Mutex($false, $SUPERVISOR_MUTEX_NAME)
    try {
        $ownsSupervisorMutex = $supervisorMutex.WaitOne(0, $false)
    } catch [System.Threading.AbandonedMutexException] {
        $ownsSupervisorMutex = $true
    }
} catch {
    Add-Content -Path $SUPERVISOR_LOG -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Khong tao/mo duoc singleton mutex: $_ - thoat de tranh chay trung." -Encoding utf8
    exit 0
}
if (-not $ownsSupervisorMutex) {
    Add-Content -Path $SUPERVISOR_LOG -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') Da co run_supervisor khac dang chay - ban khoi dong trung tu thoat." -Encoding utf8
    exit 0
}

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $SUPERVISOR_LOG -Value $line -Encoding utf8
}

function Start-Backend {
    # Cong 8010 (KHONG dung 8000 - da bi 1 du an WebChatbot khac cua dong nghiep chiem tren may nay)
    Start-Process -FilePath "python" -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8010" `
        -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$LOG_DIR\uvicorn.log" -RedirectStandardError "$LOG_DIR\uvicorn.err.log"
}

function Start-SyncScheduler {
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", "`"$BACKEND_DIR\sync_scheduler.ps1`"") `
        -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden -PassThru
}

Log "=== Supervisor khoi dong ==="
$backendProc = Start-Backend
Log "Backend (uvicorn :8010) started, PID=$($backendProc.Id)"
$syncProc = Start-SyncScheduler
Log "Sync scheduler started, PID=$($syncProc.Id)"

while ($true) {
    Start-Sleep -Seconds $CHECK_INTERVAL_SEC

    if ($backendProc.HasExited) {
        Log "CANH BAO: Backend da thoat (ExitCode=$($backendProc.ExitCode)) -> khoi dong lai"
        $backendProc = Start-Backend
        Log "Backend restarted, PID=$($backendProc.Id)"
    }
    if ($syncProc.HasExited) {
        Log "CANH BAO: Sync scheduler da thoat (ExitCode=$($syncProc.ExitCode)) -> khoi dong lai"
        $syncProc = Start-SyncScheduler
        Log "Sync scheduler restarted, PID=$($syncProc.Id)"
    }
}
