# Hướng Dẫn Tích Hợp Next.js Chat UI Skeleton - Dược Nam Hà

Mô-đun Chat UI này được xây dựng trên framework **Next.js 14 (App Router)** và **Tailwind CSS**, cung cấp giao diện hội thoại thông minh hỗ trợ hiển thị bảng dữ liệu (Table) và câu lệnh SQL Server (T-SQL) được AI dịch.

---

## 1. Cấu trúc thư mục tích hợp khuyến nghị
Trong dự án Next.js chính thức, anh/chị đặt tệp component này theo cấu trúc sau:

```text
src/
├── app/
│   ├── chat/
│   │   └── page.tsx        <-- Sao chép file page.tsx vào đây
│   ├── layout.tsx
│   └── page.tsx
├── components/
│   └── ui/                 <-- Các UI component dùng chung
```

---

## 2. Các thư viện phụ thuộc (Dependencies)
Anh/chị cần cài đặt các thư viện sau nếu dự án chưa có:
```bash
npm install lucide-react   # Hoặc FontAwesome icons tương đương
```

---

## 3. Cấu hình Tailwind CSS
Đảm bảo file `tailwind.config.js` hoặc `tailwind.config.ts` quét toàn bộ thư mục `src`:

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-outfit)", "Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
```

---

## 4. Kết nối đến API Backend AI Chatbot
Trong file `page.tsx`, hàm `handleSend` hiện đang mô phỏng dữ liệu phản hồi (Mock). Khi kết nối trực tiếp đến API SQL Server thực tế (FastAPI hoặc Next.js API Routes), anh/chị chỉnh sửa như sau:

```typescript
const handleSend = async (e: React.FormEvent) => {
  e.preventDefault();
  if (!input.trim() || loading) return;

  const userMsg: Message = { id: Date.now().toString(), sender: 'user', text: input };
  setMessages((prev) => [...prev, userMsg]);
  setInput('');
  setLoading(true);

  try {
    const response = await fetch('/api/chat', { // Endpoint API Next.js / FastAPI
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}` 
      },
      body: JSON.stringify({ question: input.trim() })
    });
    const data = await response.json();
    
    setMessages((prev) => [
      ...prev,
      {
        id: (Date.now() + 1).toString(),
        sender: 'ai',
        text: data.answer,       // Câu trả lời tiếng Việt
        sql: data.sql,           // Câu lệnh T-SQL
        tableData: data.data     // Bảng dữ liệu JSON trả về
      }
    ]);
  } catch (error) {
    setMessages((prev) => [...prev, { id: Date.now().toString(), sender: 'ai', text: 'Không thể kết nối đến máy chủ AI.' }]);
  } finally {
    setLoading(false);
  }
};
```
---

## 5. Chạy thử nghiệm Local
Chạy lệnh khởi tạo Next.js dev server:
```bash
npm run dev
```
Truy cập `http://localhost:3000/chat` để kiểm tra trải nghiệm chat đa thiết bị (Responsive Mobile & Desktop).
