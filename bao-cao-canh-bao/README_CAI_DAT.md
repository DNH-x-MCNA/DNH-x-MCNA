# Cài đặt bộ Skill DNH vào Claude Code

## Cách 1: Merge trực tiếp vào repo (khuyến nghị)

```
git clone https://github.com/lvd192/DNH.git
cd DNH
```

Copy toàn bộ thư mục `.claude/skills/` từ gói này vào root của repo `DNH`
(merge, không ghi đè nếu repo đã có `.claude/skills/` khác):

```
xcopy /E /I <đường-dẫn-tải-về>\.claude\skills .claude\skills
```

Commit và push để cả team dùng chung:

```
git add .claude/skills
git commit -m "Add DNH Claude Code skills: project context, debt aging, NL2SQL security, onsite prep, alert builder"
git push
```

## Cách 2: Chỉ dùng cá nhân (không commit vào repo)

Copy vào `~/.claude/skills/` thay vì vào trong repo — skill sẽ áp dụng cho
mọi project bạn mở, không chỉ DNH.

## Việc cần làm SAU KHI cài đặt (quan trọng)

3 file sau đang là **placeholder**, cần điền nội dung thật lấy từ tài liệu
đã tạo ở phiên làm việc trước (không có sẵn để tự động copy vào phiên này):

1. `.claude/skills/dnh-debt-aging-schema/assets/debt_aging_schema.sql`
   → paste T-SQL schema debt aging bucket thật đã sửa theo hợp đồng.
2. `.claude/skills/dnh-email-alert-builder/references/alert_triggers.md`
   → paste chi tiết 4 trigger từ `MCNA_DNH_ProjectPlan_v3.docx`.
3. `.claude/skills/dnh-onsite-prep/references/onsite_questions.md`
   → bổ sung nếu có danh sách câu hỏi chi tiết hơn bản khung hiện tại.

Sau khi điền xong, Claude Code trong repo DNH sẽ tự động dùng đúng số liệu
thật thay vì nhắc lại "chưa chốt / cần hỏi lại".

## Danh sách skill

| Skill | Kích hoạt | Vai trò |
|---|---|---|
| `dnh-project-context` | Tự động, background | Kiến trúc & scope đã chốt |
| `dnh-debt-aging-schema` | Tự động khi động đến debt/aging | Schema công nợ chuẩn |
| `dnh-nl2sql-security` | Tự động khi động đến ai_agent/NL2SQL | Checklist bảo mật bắt buộc |
| `dnh-onsite-prep` | Thủ công `/dnh-onsite` | Câu hỏi + checklist onsite |
| `dnh-email-alert-builder` | Tự động khi viết code alert | 4 trigger + skeleton script |
