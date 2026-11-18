import type { Metadata, Viewport } from "next";
import { Inter, Outfit } from "next/font/google";

import { OfflineBanner } from "@/components/offline-banner";
import { DARK_BAR, THEME_SCRIPT } from "@/lib/theme";

import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const outfit = Outfit({
  variable: "--font-outfit",
  weight: "800",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Sukat",
  description: "Inventory and sales for Philippine hardware stores",
  appleWebApp: { capable: true, title: "Sukat", statusBarStyle: "default" },
  icons: {
    icon: [{ url: "/mascot/sukat-mark-small.svg", type: "image/svg+xml" }],
    apple: "/apple-touch-icon.png",
  },
};

export const viewport: Viewport = {
  themeColor: DARK_BAR,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-theme="dark" className={`${inter.variable} ${outfit.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full flex flex-col font-sans">
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <OfflineBanner />
        {children}
      </body>
    </html>
  );
}
