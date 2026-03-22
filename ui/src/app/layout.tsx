import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CryptoMega Dashboard",
  description: "Real-time crypto signal tournament dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg font-mono text-gray-200">
        {children}
      </body>
    </html>
  );
}
