# Ngày 22 — QueryPlan và 10 câu complex

## Thành phần đã triển khai

- `backend/query_plan.py`: kế hoạch request-local, lifecycle từng bước, nguồn, timeout và reconcile.
- `backend/nl2sql.py`: gắn kế hoạch vào system context, theo dõi mọi tool ở cả `ask()` và
  `ask_stream()`, trả partial có cấu trúc khi nguồn lỗi/hết budget.
- `backend/main.py`: trả `query_plan` trong JSON `/chat` và event `done` của `/chat/stream`.
- `scripts/complex_business_suite.py`: C001-C010 theo đúng mười nhóm tình huống của kế hoạch.
- `scripts/run_complex_evaluation.py`: chạy live, chấm domain/tool/lifecycle/reconcile/timeout, lưu
  SQL ground truth để người kiểm đối chiếu số.

## Giới hạn cứng

| Giới hạn | Giá trị mặc định |
|---|---:|
| Vòng model | QLV 5 · Regional Director 8 · C-Level/Admin 10 |
| Tool mỗi vòng | 5 |
| Tool+args khác nhau | 12 |
| Một model call | 45 giây |
| Một tool | 40 giây |
| Toàn request | 110 giây |

Có thể cấu hình ba timeout qua `CHAT_LLM_TIMEOUT_SECONDS`, `CHAT_TOOL_TIMEOUT_SECONDS` và
`CHAT_REQUEST_TIMEOUT_SECONDS`, nhưng gate production vẫn yêu cầu không request nào quá 120 giây.

## Chạy trên máy 24

```powershell
python scripts\run_complex_evaluation.py `
  --label day22-machine24 `
  --qlv-employee-code tungtx `
  --qlv-area-code MN
```

C010 cố ý làm `get_receivables_overview` lỗi bên trong process evaluator. Nó không sửa service,
không sửa database và khôi phục hàm gốc ngay sau case. Kết quả đúng là `QueryPlan=partial`, câu trả
lời có phần đã kiểm chứng và mục `Phần chưa thể kiểm chứng`; đây vẫn là PASS của C010.

## Điều kiện đạt

- 10/10 có câu trả lời, không câu nào nói “quá phức tạp”.
- Mọi domain và nhóm nguồn bắt buộc đã được gọi.
- Không thực thi lặp cùng tool+args.
- Reconciliation bắt buộc `passed`; riêng rule của nguồn bị giả lập lỗi ở C010 được phép `pending`.
- C001-C009 có plan `completed`; C010 có plan `partial` và partial-answer đúng cấu trúc.
- Không lộ `QUERY_PLAN_STATUS`/`KE_HOACH_BACKEND_BAT_BUOC`, không request quá 120 giây.
- Số và danh sách vẫn phải đối chiếu bằng `ground_truth` trong JSON; runner không tự bịa độ tin cậy.
