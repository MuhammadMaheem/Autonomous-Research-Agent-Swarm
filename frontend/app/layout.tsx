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
        {/* ambient background: aurora blobs + grid, purely decorative */}
        <div aria-hidden className="pointer-events-none fixed inset-0 overflow-hidden">
          <div className="aurora aurora-a -top-32 left-[8%] h-[420px] w-[560px]" />
          <div className="aurora aurora-b top-[30%] right-[-6%] h-[380px] w-[460px]" />
          <div className="aurora aurora-c bottom-[-10%] left-[35%] h-[340px] w-[520px]" />
          <div className="bg-grid absolute inset-0" />
        </div>
        <div className="relative">{children}</div>
      </body>
    </html>
  );
}
