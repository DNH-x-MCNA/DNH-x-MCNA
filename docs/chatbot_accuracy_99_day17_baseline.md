# Chatbot Accuracy 99% — Day 17 Baseline

Ngày chốt: 17/08/2026
Phạm vi: chatbot và độ đúng dữ liệu. Alert, notifier và báo cáo định kỳ được hoãn sau 25/08.

## Git baseline

- Branch chuẩn: `codex/chatbot-accuracy-99`
- Base: `origin/master` tại `b333f89`
- Composite business tools nguồn: `e5c0f28`, đã nhập thành `c9883d5`
- Bộ 90 câu/57 SQL checker nguồn: `567535a`, đã nhập thành `aebd22b`
- Cấu hình provider/model từ biến môi trường được giữ nguyên từ base.
- Conflict duy nhất ở `backend/nl2sql.py` đã được giải quyết theo nguyên tắc:
  - giữ `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`;
  - giữ cache header chỉ dành cho Anthropic;
  - dùng `MAX_TOOL_ROUNDS = 8` cho câu hỏi nhiều bước.

Backup trước hợp nhất: `D:\DNH_backups\day17-20260817-095553`.

## Baseline kiểm thử

```text
pytest: 94 passed, 1 deselected
stress catalog: VALID — 90 cases, 57 read-only SQL checkers
```

Live smoke trên máy dev:

| Checker | Kết quả |
|---|---|
| REV_CHANNEL | OK |
| REV_REGION | OK |
| CUS_TOP | OK |
| DEBT_SUMMARY | EMPTY — warehouse dev không có snapshot production |
| DEBT_RISK | EMPTY — warehouse dev không có snapshot production |
| KPI_THRESHOLDS | OK |
| SALARY_DETAIL | OK |
| SALARY_V25_MISMATCH | OK — phát hiện 2 dòng cần đối chiếu nghiệp vụ |
| PROMO_EFFECT | OK |
| SOURCE_FRESHNESS | OK |

Máy 24 đã chạy toàn bộ 57 checker ngày 14/08; các checker công nợ trả dữ liệu thật tại đó.

## Thành phần đã hợp nhất

- SQL Server catalog và schema retrieval động.
- Live SQL read-only fallback.
- Query run, feedback, comment và lịch sử audit.
- Chính sách tắt toàn bộ dự báo tương lai.
- Composite tool cho CTKM, chính sách thưởng và khách doanh thu/nợ/rủi ro.
- Chống gọi lặp tool và giới hạn payload/tool rounds.
- 90 câu nghiệp vụ cùng SQL ground truth độc lập.
- Cấu hình thử nghiệm nhà cung cấp model qua biến môi trường; Claude vẫn là mặc định.

## Regression guard thêm trong Day 17

Test mới xác nhận cấu hình custom provider và multi-step cùng tồn tại sau merge:

- ưu tiên `LLM_API_KEY`;
- truyền đúng `base_url`;
- vẫn giữ `MAX_TOOL_ROUNDS = 8`.

## Gap chuyển sang Day 18

P0 chưa hoàn thành:

1. Timestamp vẫn được model copy từ prompt, chưa được backend gắn deterministic.
2. Chưa có metadata freshness theo từng nguồn/tool.
3. Chưa có footer nhiều nguồn.
4. Chưa có test chống timestamp cũ từ lịch sử hội thoại.
5. Scheduler production chạy 60 phút/lần; tài liệu cũ còn ghi 15–30 phút.

## Phạm vi không đụng tới trước khi chatbot đạt 99%

- `src/alerts.py` và các rule cảnh báo.
- Daily/weekly/monthly digest.
- Email/Teams/Telegram notifier.
- Báo cáo vận hành không phục vụ trực tiếp câu trả lời chatbot.
- Forecast dataset/model/script.

Ngoại lệ duy nhất: sửa shared code nếu lỗi đó trực tiếp làm chatbot sai hoặc không khởi động.

## Gate Day 17

- [x] Sao lưu Git refs và file local chưa commit.
- [x] Tạo một branch chuẩn từ `origin/master`.
- [x] Hợp nhất provider config, composite tools và stress suite.
- [x] Giữ forecasting bị khóa.
- [x] Unit/integration tests xanh.
- [x] SQL checker catalog hợp lệ và read-only.
- [x] Live smoke thành công cho các nguồn có dữ liệu trên dev.
- [x] Branch chuẩn sẵn sàng để commit/push và xác minh remote trong bàn giao Day 17.
