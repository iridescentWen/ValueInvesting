import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ValueInvesting",
  description: "AI agent for value investing",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">{children}</body>
    </html>
  );
}
