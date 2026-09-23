# Runbook triển khai máy 24

*Lập 23/09/2026, sau một đợt pull–restart hụt hai lần trong cùng một buổi.*

Máy 24 là máy chạy chatbot thật. Theo `AGENTS.md`: **không sửa code trên máy 24**, máy 24 chỉ
`git pull` bản đã test rồi khởi động lại dịch vụ.

## Thực tế trên máy 24 (đo 23/09/2026)

| | Giá trị |
|---|---|
| Repo | `C:\dnh_chatbot` |
| Service chatbot | `DNH_Chatbot_Backend` |
| Service cảnh báo | `DNH_Realtime_Alerts` |
| Service tunnel | `DNH_Chatbot_Tunnel` (Cloudflare) |
| Log | `C:\dnh_chatbot\backend\logs\` |
| Kho | `C:\dnh_chatbot\backend\warehouse.db`, `memory.db`, `auth.db` |

**Không có `sqlite3` CLI trên máy 24** — mọi truy vấn phải qua `python -c` hoặc script Python.

### Thư mục nào đổi thì restart service nào

Ba service độc lập nhau và **nạp code từ những thư mục khác nhau**. Restart theo đúng bảng này:

| Thư mục có thay đổi | Service cần restart |
|---|---|
| `backend/` | `DNH_Chatbot_Backend` |
| `src/` | `DNH_Realtime_Alerts` |
| cả hai | cả hai |
| `docs/`, `scripts/`, `tests/` | không cần restart gì |

> **Bẫy đã gặp 23/09:** bản runbook đầu chỉ ghi *"vá code trong `backend/` thì chỉ restart
> `DNH_Chatbot_Backend`"*. Đợt deploy hôm đó có PR #54 sửa `src/alerts.py`, nên chatbot được nạp
> code mới còn **service cảnh báo vẫn chạy bản cũ** — không ai để ý vì service vẫn `Running` và
> chatbot thì đã đúng. Chỉ phát hiện nhờ nhìn `StartTime` của tiến trình còn lại vẫn là ngày hôm
> trước.

Sau khi `git pull`, xem thư mục nào vừa đổi để biết phải restart cái nào:

```powershell
git -C C:\dnh_chatbot diff --name-only HEAD@{1} HEAD | ForEach-Object { ($_ -split '/')[0] } | Sort-Object -Unique
```

⚠️ `scripts/register_chatbot_web_service.bat` **không phải lệnh restart** — nó `nssm remove` rồi
cài lại service từ đầu. Chỉ dùng khi đăng ký lần đầu hoặc cố ý cài lại.

## Quy trình triển khai

Thứ tự bắt buộc: **pull trước, restart sau**. Restart trước khi pull là vô ích — tiến trình nạp lại
đúng bản code cũ.

**1. Pull**

```powershell
git -C C:\dnh_chatbot pull --ff-only origin master
git -C C:\dnh_chatbot rev-parse --short HEAD
git -C C:\dnh_chatbot status --short
```

`rev-parse` phải ra đúng commit mong đợi, `status` phải sạch. Nếu `--ff-only` lỗi thì **dừng**,
đừng `--force` hay `reset` — có thể máy 24 đang ở nhánh khác hoặc có commit cục bộ cần review.

**2. Kiểm code trên đĩa đã mới**

```powershell
python -c "import sys; sys.path.insert(0,r'C:\dnh_chatbot\backend'); import report_templates as rt; print(rt.__file__)"
```

Kiểm bằng một **thứ chỉ có ở bản mới** (hàm/trường mới thêm), không kiểm bằng giá trị mà bản cũ
cũng trả đúng. Bài học 23/09: phép kiểm `_detail_cutoff() == '2024-01-01'` đạt trên **cả** hai bản
vì hằng số cũ trùng giá trị mong đợi — không chứng minh được gì.

**3. Restart** (PowerShell quyền Administrator) — theo bảng thư mục ở trên

```powershell
Restart-Service DNH_Chatbot_Backend -Force
```

Nếu `src/` cũng đổi thì restart thêm:

```powershell
Restart-Service DNH_Realtime_Alerts -Force
```

**4. Xác nhận tiến trình đã khởi động lại**

```powershell
Get-Service DNH_Chatbot_Backend, DNH_Realtime_Alerts | Select-Object Name, Status
Get-Process python* -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime | Format-Table -AutoSize
```

`StartTime` của **mọi service vừa restart** phải là hôm nay, sau thời điểm pull. Máy 24 luôn có
nhiều tiến trình python (chatbot, cảnh báo, sync scheduler); cái **cố ý không restart** thì giữ giờ
cũ là đúng — nhưng phải đối chiếu với bảng thư mục để biết cái nào là cố ý, cái nào là bỏ sót.

**Đừng kill tiến trình python bằng tay** để "restart": rất dễ giết nhầm sync scheduler, mất lịch
đồng bộ Bravo.

## Bẫy đã gặp

| Bẫy | Dấu hiệu |
|---|---|
| Restart mà chưa pull | `rev-parse` vẫn ra commit cũ; code trên đĩa không đổi |
| Pull rồi mà quên restart | Đĩa mới nhưng `StartTime` của tiến trình vẫn là hôm trước |
| Restart thiếu service | Chỉ restart chatbot trong khi `src/` cũng đổi → cảnh báo vẫn chạy code cũ, service vẫn `Running` nên không có dấu hiệu gì |
| Tên service sai | `Restart-Service : Cannot find any service with service name` — file `.bat` trong repo từng ghi `DNH_Chatbot_Web`, thực tế là `DNH_Chatbot_Backend` |
| Phép kiểm không phân biệt được bản cũ/mới | Báo "ĐẠT" trên cả hai bản, che mất việc chưa pull |

## Đọc log và kho (miễn phí, không gọi model)

`query_runs` trong `memory.db` giàu hơn log chi phí nhiều: có `answer`, `sql_used_json`,
`error_message`, `feedback_rating/category/comment`.

**`audit_log.jsonl` ghi giờ ĐỊA PHƯƠNG, `query_runs.created_at` ghi UTC — lệch đúng 7 tiếng.**
Lọc theo `session_id` thay vì theo giờ để khỏi tìm trượt.
