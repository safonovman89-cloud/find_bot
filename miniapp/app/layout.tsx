import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "База знаний ЯНАО",
  description: "Поиск инструкций и документов по информационным системам ЯНАО.",
  openGraph: {
    title: "База знаний ЯНАО",
    description: "Ответы по системам — в одном месте",
    type: "website",
    locale: "ru_RU",
    images: [{ url: "/og.png", width: 1731, height: 909, alt: "База знаний ЯНАО" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "База знаний ЯНАО",
    description: "Ответы по системам — в одном месте",
    images: ["/og.png"],
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
        <script src="https://st.max.ru/js/max-web-app.js" defer />
      </body>
    </html>
  );
}
