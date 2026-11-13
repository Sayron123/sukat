import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import { OfflineBanner } from "@/components/offline-banner";
import { THEME_SCRIPT } from "@/lib/theme";

import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Sukat",
  description: "Inventory and sales for Philippine hardware stores",
  appleWebApp: { capable: true, title: "Sukat", statusBarStyle: "default" },
  icons: { apple: "/apple-touch-icon.png" },
};

export const viewport: Viewport = {
  themeColor: "#f5f5f4",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full flex flex-col font-sans">
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <OfflineBanner />
        {children}
      </body>
    </html>
  );
}
