import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stage 1 Evaluation",
  description: "Hackathon submission scoring, ranking, and top-10 shortlist",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
