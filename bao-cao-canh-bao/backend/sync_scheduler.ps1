# === Dong bo dinh ky kho local (SQLite) tu Bravo, moi 20 phut ===
# Chi dong bo GIA TANG (10 ngay gan nhat + cac bang nho) - khong chay --full lai (da chay 1 lan).
#
# LUU Y (7/2026): pattern cu "& $PYTHON $SCRIPT 2>&1 | ForEach-Object {...}" tung bi TREO VINH VIEN
# (PowerShell pipe deadlock) dung ngay sau khi may vua khoi dong/wake - tien trinh python ben trong
# da thoat nhung vong lap PowerShell ben ngoai khong bao gio nhan ra, chan ca chu ky dong bo tiep theo.
# Doi sang Start-Process + WaitForExit co TIMEOUT: neu 1 lan chay qua lau, tu huy va thu lai chu ky sau.
$INTERVAL_MIN = 20
$RETRY_SEC = 60     # neu lan chay vua roi loi/treo, thu lai sau khoang ngan nay thay vi doi du 20 phut
$TIMEOUT_SEC = 90   # qua thoi gian nay coi nhu treo, huy tien trinh (da giam nho Bravo engine gio co
                     # Connection Timeout=15s rieng - binh thuong 1 lan chay chi mat vai giay)
$PYTHON = "C:\Users\DANG TRIEU\AppData\Local\Programs\Python\Python311\python.exe"
$SCRIPT = "C:\Users\DANG TRIEU\dnh_chatbot\backend\sync_warehouse.py"
$LOG = "C:\Users\DANG TRIEU\dnh_chatbot\backend\logs\sync_scheduler.log"
$TMP_OUT = "C:\Users\DANG TRIEU\dnh_chatbot\backend\logs\sync_scheduler_run.log"
$TMP_ERR = "C:\Users\DANG TRIEU\dnh_chatbot\backend\logs\sync_scheduler_run.err.log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $LOG -Value $line -Encoding utf8
}

Log "Sync scheduler khoi dong, dong bo moi $INTERVAL_MIN phut (timeout $TIMEOUT_SEC s/lan)..."

while ($true) {
    Log "Bat dau dong bo gia tang..."
    try {
        if (Test-Path $TMP_OUT) { Remove-Item $TMP_OUT -Force }
        if (Test-Path $TMP_ERR) { Remove-Item $TMP_ERR -Force }

        $proc = Start-Process -FilePath $PYTHON -ArgumentList "`"$SCRIPT`"" -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $TMP_OUT -RedirectStandardError $TMP_ERR

        $finished = $proc.WaitForExit($TIMEOUT_SEC * 1000)
        $ok = $false

        if (-not $finished) {
            Log "CANH BAO: dong bo qua $TIMEOUT_SEC s (treo) - huy tien trinh, thu lai sau $RETRY_SEC s."
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        } else {
            # Goi lai WaitForExit() khong tham so (blocking) de dam bao ExitCode da duoc dong bo day du -
            # tung gap loi ExitCode doc ve rong ($null) ngay sau ban WaitForExit(timeout) du tien trinh
            # da thuc su ket thuc thanh cong, khien code hieu nham la that bai va lap lien tuc khong can thiet.
            $proc.WaitForExit()
            Get-Content $TMP_OUT -ErrorAction SilentlyContinue | ForEach-Object { Log "  $_" }
            Get-Content $TMP_ERR -ErrorAction SilentlyContinue | ForEach-Object { Log "  $_" }
            Log "Dong bo xong (ExitCode=$($proc.ExitCode))."
            $ok = ($proc.ExitCode -eq 0)
            if (-not $ok) { Log "CANH BAO: exit code khac 0 - thu lai sau $RETRY_SEC s." }
        }
    } catch {
        Log "LOI dong bo: $($_.Exception.Message)"
        $ok = $false
    }

    if ($ok) {
        Start-Sleep -Seconds ($INTERVAL_MIN * 60)
    } else {
        Start-Sleep -Seconds $RETRY_SEC
    }
}
