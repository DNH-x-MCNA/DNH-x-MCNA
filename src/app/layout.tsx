import type { Metadata, Viewport } from "next";
import { Inter, Geist_Mono } from "next/font/google";
import "./globals.css";

// Inter thay Geist theo yêu cầu Executive Light Theme 29/07/2026. Bắt buộc có subset "vietnamese"
// (không chỉ "latin") — nếu thiếu, các ký tự có dấu (ư, ơ, đ, các dấu thanh...) sẽ rơi về font dự
// phòng của hệ điều hành, phá vỡ tính nhất quán của bộ chữ trên toàn app.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "vietnamese"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DNH AI Analyst · Dược Nam Hà",
  description: "Trợ lý AI phân tích dữ liệu kinh doanh — Công ty Cổ phần Dược Nam Hà",
};

export const viewport: Viewport = {
  themeColor: "#ffffff",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="vi"
      className={`${inter.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full font-sans">{children}</body>
    </html>
  );
}
