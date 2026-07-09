import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Research Agent Swarm",
  description: "Autonomous multi-agent research with citation auditing",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
