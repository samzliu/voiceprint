import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Voiceprint — write in a trained human voice",
  description:
    "Try a writing model trained on one person's prose. Give it the facts; Voiceprint writes the draft.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
  openGraph: {
    title: "Voiceprint — your prose, compressed",
    description: "Train an open model on writing you actually wrote, then draft from facts in your voice.",
    images: [{ url: "/voiceprint-social.png", width: 1536, height: 1024, alt: "Voiceprint wordmark beside a voice trace forming a fingerprint" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Voiceprint — your prose, compressed",
    description: "Train an open model on writing you actually wrote.",
    images: ["/voiceprint-social.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
