import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Research Agent Swarm",
  description: "Autonomous multi-agent research with citation auditing",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        {/* ambient background: radial wash + dot grid, decorative */}
        <div aria-hidden className="pointer-events-none fixed inset-0 overflow-hidden bg-radial-wash">
          <div className="bg-dot-grid absolute inset-0" />
        </div>
        <div className="relative z-10">{children}</div>
      </body>
    </html>
  );
}
