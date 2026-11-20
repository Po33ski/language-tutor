import type { Metadata, Viewport } from "next";
import { Atkinson_Hyperlegible_Next } from "next/font/google";
import { AuthGate } from "@/components/auth/auth-gate";

import "./globals.css";

// Designed for legibility: letters that are easy to confuse (I/l/1, a/o, rn/m) stay
// distinct, which matters when a correction hinges on a single letter or article.
const atkinson = Atkinson_Hyperlegible_Next({
  variable: "--font-atkinson",
  subsets: ["latin"],
  // Next has no fallback metrics for this font yet (it warns on every build); the font
  // is self-hosted and preloaded, so the system-font fallback shows only briefly.
  adjustFontFallback: false,
  fallback: ["system-ui", "sans-serif"],
});

export const metadata: Metadata = {
  title: "Language Tutor",
  description: "Practice English through conversation with an AI tutor.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${atkinson.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-paper font-sans text-ink">
        <AuthGate>{children}</AuthGate>
      </body>
    </html>
  );
}
