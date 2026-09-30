# Scheduler 255 và gửi thử email QLV — 28/09/2026

Phần Codex trong kế hoạch nghiệm thu 10/10. Code runner đã trả 0 khi báo cáo thành
công, 1 khi báo cáo trả thất bại hoặc ném exception. Chưa có Action và log cùng lần
chạy trên máy 24 để kết luận nguyên nhân mã 255 hiện tại.

## Kiểm Scheduled Task, không chạy báo cáo

Chạy PowerShell trên máy 24. Khối sau chỉ đọc metadata của ba task; không chạy task,
không gửi email/Teams, không gọi Bravo/model, không thay đổi lịch hoặc dịch vụ.
Chỉ xuất các cờ nhận diện Action, không in Arguments, XML task hay giá trị bí mật.
Đường dẫn máy 24 bên dưới lấy từ [runbook triển khai](runbook_trien_khai_may_24.md)
(ghi nhận 23/09); nếu repo đã chuyển chỗ, dùng đường dẫn thực tế đã xác minh trên máy.

```powershell
$periods = [ordered]@{
    DNH_Daily_Digest_1745 = 'daily'
    DNH_Weekly_Report = 'weekly'
    DNH_Monthly_Report = 'monthly'
}
foreach ($name in $periods.Keys) {
    try {
        $task = Get-ScheduledTask -TaskName $name -TaskPath '\' -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -InputObject $task -ErrorAction Stop
        $actions = @($task.Actions)
        foreach ($action in $actions) {
            $exe = [System.IO.Path]::GetFileName(([string]$action.Execute).Trim('"'))
            $argsText = [string]$action.Arguments
            [pscustomobject]@{
                Task = $name
                State = [string]$task.State
                LastRunTime = $info.LastRunTime
                LastTaskResult = $info.LastTaskResult
                LastResultHex = ('0x{0:X8}' -f [long]$info.LastTaskResult)
                NextRunTime = $info.NextRunTime
                ActionCount = $actions.Count
                PythonAction = $exe -match '^python(?:\d+(?:\.\d+)*)?\.exe$'
                ShellAction = $exe -in @('cmd.exe', 'powershell.exe', 'pwsh.exe')
                MentionsRunner = $argsText -match 'run_digest_task\.py'
                MentionsMain = $argsText -match 'main\.py'
                MentionsExpectedPeriod = $argsText -match ('\b' + $periods[$name] + '\b')
                HasOverride = $argsText -match '--(?:email|teams-webhook)-override'
                HasWorkingDirectory = -not [string]::IsNullOrWhiteSpace($action.WorkingDirectory)
                RunsAsSystem = $task.Principal.UserId -in @('SYSTEM', 'NT AUTHORITY\SYSTEM', 'S-1-5-18')
            }
        }
        if ($actions.Count -eq 0) {
            [pscustomobject]@{ Task = $name; ReadStatus = 'NO_ACTION' }
        }
    } catch {
        # Exception text can include command arguments. Keep the output generic.
        [pscustomobject]@{ Task = $name; ReadStatus = 'UNAVAILABLE_CHECK_LOCALLY' }
    }
}
```

Các cờ `Mentions*` chỉ hỗ trợ tìm Action cũ; chúng không xác nhận đường dẫn hay lệnh
đúng. Kiểm trực tiếp tab **Actions** trên máy: chương trình phải là Python đã cài,
argument là `"C:\dnh_chatbot\scripts\run_digest_task.py" daily` (hoặc `weekly`,
`monthly` tương ứng). Không dán nguyên Action vào chat nếu có webhook/mật khẩu.

Đối chiếu `LastRunTime` với mốc `===== ... --send-daily/weekly/monthly =====` và
dòng `[TASK]` kết thúc trong `C:\dnh_chatbot\logs\daily_digest.log`,
`weekly_report.log`, `monthly_report.log`. Xem log trực tiếp, che bí mật trước khi
chia sẻ trích đoạn. Nếu tiến trình còn `Running`, LastTaskResult chưa phải kết quả
cuối của lượt đang chạy. HTTP 202/2xx chỉ xác nhận Flow nhận request, chưa chứng minh
người dùng nhận card.

**Git pull và restart `DNH_Realtime_Alerts` không cập nhật Action Scheduled Task.**
Nếu Action còn wrapper cũ, cần đổi đúng Action sau khi xác minh; giữ nguyên lịch,
tài khoản và các thiết lập khác. Không chạy lại `register_digest_schedule.bat`
chỉ để kiểm tra vì script đó ghi đè ba task. Không ép mã thoát 0 để che lỗi gửi.
Chỉ đóng mục 255 khi đã xác nhận Action và kết quả của lần chạy thực tế tương ứng.

## Chuẩn bị gửi thử email QLV trước 06/10

Chờ DNH cấp SMTP, địa chỉ From và email QLV gắn đúng `employee_code`, `region`,
`channel`; giữ C-Level/GĐ miền/GĐ kênh nhận Teams theo #112. Đặc tả và cách đặt biến
SMTP: [chuẩn bị mail DNH](chuan_bi_mail_dnh_22-09.md). UPN/shared Flow là phần cấu
hình riêng; thiếu Teams không ngăn luồng email QLV đã cấu hình đúng.

Runner Daily đã chuyển tiếp `--email-override` sang hàm gửi báo cáo. Khi thử,
**luôn chọn `--audience` đúng một QLV/ASM/RM**: email override không lọc audience
và không chặn Teams cho lãnh đạo. Chạy Daily không có audience vẫn xử lý toàn bộ
danh sách người nhận. `--dry-run` không gửi nhưng vẫn dựng dữ liệu báo cáo, có thể
truy Bravo; không dùng nó làm phép kiểm Scheduler thuần metadata ở trên.

Mẫu lệnh để anh Đăng chạy sau khi đã có cấu hình và hộp thư thử được duyệt (thay
hai giá trị mẫu, không chạy nguyên mẫu):

```powershell
python C:\dnh_chatbot\scripts\run_digest_task.py daily --audience '<audience QLV đã xác nhận>' --email-override '<hộp thư thử được duyệt>'
$LASTEXITCODE
```

Lưu mốc chạy, audience, mã thoát và xác nhận thư trong hộp thư thử. Lượt thử phải
chỉ tới hộp thư override. Khi DNH xác nhận thực nhận, mới mở danh sách gửi định kỳ
đã duyệt. Unit test dùng dữ liệu/transport giả không thay cho bước thực nhận này.
