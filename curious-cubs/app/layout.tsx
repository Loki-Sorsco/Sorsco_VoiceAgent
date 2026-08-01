import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Curious Cubs — Fun Live Webinars for Kids",
  description:
    "Live, interactive online webinars for curious little minds. Art, science, stories and more — see the schedule and book a spot.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
