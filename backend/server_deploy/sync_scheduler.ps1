# === Dong bo du lieu tu Bravo (ket noi TRUC TIEP, khong qua VPN) tren may chu DNH ===
# Lich: dinh ky moi 60 phut + 1 lan DAC BIET ngay sau 17h30 (gio DNH dong don/chot phieu trong ngay)
# de lay dung so lieu da chot. Kiem tra moi 5 phut xem co den luc dong bo chua (tach rieng "kiem tra"
# va "hanh dong" de xu ly duoc ca 2 loai lich mot cach don gian, khong can tinh toan thoi gian ngu phuc tap).
$CHECK_INTERVAL_SEC = 300
$REGULAR_INTERVAL_MIN = 60
$SPECIAL_HOUR = 17
$SPECIAL_MIN = 30
$TIMEOUT_SEC = 90
$RETRY_SEC = 60

$PYTHON = "python"
$SCRIPT = "C:\dnh_chatbot\backend\sync_warehouse.py"
$LOG = "C:\dnh_chatbot\backend\logs\sync_scheduler.log"
$TMP_OUT = "C:\dnh_chatbot\backend\logs\sync_scheduler_run.log"
$TMP_ERR = "C:\dnh_chatbot\backend\logs\sync_scheduler_run.err.log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $LOG -Value $line -Encoding utf8
}

function Do-Sync {
    try {
        if (Test-Path $TMP_OUT) { Remove-Item $TMP_OUT -Force }
        if (Test-Path $TMP_ERR) { Remove-Item $TMP_ERR -Force }

        $proc = Start-Process -FilePath $PYTHON -ArgumentList "`"$SCRIPT`"" -WindowStyle Hidden -PassThru `
            -WorkingDirectory "C:\dnh_chatbot\backend" -RedirectStandardOutput $TMP_OUT -RedirectStandardError $TMP_ERR

        $finished = $proc.WaitForExit($TIMEOUT_SEC * 1000)

        if (-not $finished) {
            Log "CANH BAO: dong bo qua $TIMEOUT_SEC s (treo) - huy tien trinh."
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            return $false
        }
        # Goi lai WaitForExit() khong tham so de dam bao ExitCode da dong bo day du truoc khi doc -
        # tranh doc phai $null ngay sau khi tien trinh vua ket thuc thanh cong.
        $proc.WaitForExit()
        Get-Content $TMP_OUT -ErrorAction SilentlyContinue | ForEach-Object { Log "  $_" }
        Get-Content $TMP_ERR -ErrorAction SilentlyContinue | ForEach-Object { Log "  $_" }
        Log "Dong bo xong (ExitCode=$($proc.ExitCode))."
        return ($proc.ExitCode -eq 0)
    } catch {
        Log "LOI dong bo: $($_.Exception.Message)"
        return $false
    }
}

Log "=== Sync scheduler (may chu DNH, ket noi truc tiep) khoi dong ==="
$lastRunTime = Get-Date -Year 2000 -Month 1 -Day 1
$lastSpecialRunDate = ""

while ($true) {
    $now = Get-Date
    $todayStr = $now.ToString("yyyy-MM-dd")
    $minutesSinceLastRun = ($now - $lastRunTime).TotalMinutes
    $isSpecialWindow = ($now.Hour -eq $SPECIAL_HOUR -and $now.Minute -ge $SPECIAL_MIN -and $now.Minute -lt ($SPECIAL_MIN + 5))
    $needSpecialRun = ($isSpecialWindow -and $lastSpecialRunDate -ne $todayStr)

    if ($minutesSinceLastRun -ge $REGULAR_INTERVAL_MIN -or $needSpecialRun) {
        $reason = if ($needSpecialRun) { "DAC BIET sau 17h30 (chot phieu)" } else { "dinh ky moi $REGULAR_INTERVAL_MIN phut" }
        Log "Bat dau dong bo ($reason)..."
        $ok = Do-Sync
        if ($ok) {
            $lastRunTime = $now
            if ($needSpecialRun) { $lastSpecialRunDate = $todayStr }
        } else {
            Log "Se thu lai o lan kiem tra sau (~$RETRY_SEC-$CHECK_INTERVAL_SEC s nua)."
        }
    }

    Start-Sleep -Seconds $CHECK_INTERVAL_SEC
}
