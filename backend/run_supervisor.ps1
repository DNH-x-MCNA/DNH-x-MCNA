# === Giam sat & tu khoi dong lai: Backend + Sync Scheduler + Cloudflared ===
# (May chu DNH - ket noi Bravo TRUC TIEP, khong qua VPN)
# 23/07/2026: BO HAN Telegram Bot khoi bundle nay - kenh chat da chuyen han sang web (dnh-bot.vercel.app),
# Telegram khong con dung. Day cung la nguon sinh tien trinh mo coi: moi lan supervisor nay tu khoi dong
# lai (reboot/restart thu cong) se spawn 1 the he telegram_bot.py MOI ma KHONG kill the he cu (bien
# $botProc chi ton tai trong phien PowerShell hien tai, tien trinh con cu bi "mo coi" khi cha restart) -
# phat hien thuc te 23/07/2026: 4 tien trinh telegram_bot.py song song, tao ngay 16/07, 20/07, 21/07,
# 22/07, khong cai nao chet. Xem docs/kich_ban_demo1_chatbot.md (repo D:\DNH) va memory
# may24_orphan_process_duplication cho boi canh day du ve lop loi nay.
$BACKEND_DIR = "C:\dnh_chatbot\backend"
$LOG_DIR = "$BACKEND_DIR\logs"
$SUPERVISOR_LOG = "$LOG_DIR\supervisor.log"
$CHECK_INTERVAL_SEC = 30

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

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

function Start-CloudflaredSupervisor {
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", "`"$BACKEND_DIR\cloudflared_supervisor.ps1`"") `
        -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden -PassThru
}

Log "=== Supervisor khoi dong ==="
$backendProc = Start-Backend
Log "Backend (uvicorn :8010) started, PID=$($backendProc.Id)"
$syncProc = Start-SyncScheduler
Log "Sync scheduler started, PID=$($syncProc.Id)"
$cfProc = Start-CloudflaredSupervisor
Log "Cloudflared supervisor started, PID=$($cfProc.Id)"

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
    if ($cfProc.HasExited) {
        Log "CANH BAO: Cloudflared supervisor da thoat (ExitCode=$($cfProc.ExitCode)) -> khoi dong lai"
        $cfProc = Start-CloudflaredSupervisor
        Log "Cloudflared supervisor restarted, PID=$($cfProc.Id)"
    }
}
