"use client";

import { useState } from "react";

import { ChatPanel } from "@/components/layout/chat-panel";
import { CommandPalette } from "@/components/layout/command-palette";
import { NavRail } from "@/components/layout/nav-rail";
import { TopBar } from "@/components/layout/top-bar";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { I18nProvider } from "@/lib/i18n";
import { useAppStore } from "@/lib/store";

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const [commandOpen, setCommandOpen] = useState(false);
  const locale = useAppStore((s) => s.locale);
  const chatOpen = useAppStore((s) => s.chatPanelOpen);
  const chatWidth = useAppStore((s) => s.chatPanelWidth);
  const setChatWidth = useAppStore((s) => s.setChatPanelWidth);

  // 折叠时右栏用固定 40px 的独立 div（不进 ResizablePanelGroup），
  // 展开时把右栏挂进 PanelGroup 以便拖动。
  return (
    <I18nProvider locale={locale}>
    <div className="flex h-dvh flex-col">
      <TopBar onOpenCommand={() => setCommandOpen(true)} />

      <div className="flex min-h-0 flex-1">
        <NavRail />

        <div className="min-h-0 flex-1">
          {chatOpen ? (
            <ResizablePanelGroup
              direction="horizontal"
              onLayout={(sizes: number[]) => {
                const total =
                  typeof window !== "undefined" ? window.innerWidth - 56 : 1200;
                const right = (sizes[1] / 100) * total;
                setChatWidth(Math.round(right));
              }}
            >
              <ResizablePanel defaultSize={100 - pct(chatWidth)} minSize={30}>
                <main className="h-full overflow-auto">{children}</main>
              </ResizablePanel>
              <ResizableHandle withHandle />
              <ResizablePanel
                defaultSize={pct(chatWidth)}
                minSize={20}
                maxSize={45}
              >
                <ChatPanel />
              </ResizablePanel>
            </ResizablePanelGroup>
          ) : (
            <div className="flex h-full">
              <main className="min-h-0 flex-1 overflow-auto">{children}</main>
              <ChatPanel />
            </div>
          )}
        </div>
      </div>

      <CommandPalette open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
    </I18nProvider>
  );
}

/** chatWidth(px) → 初始百分比（基于典型 viewport 1440-56=1384，仅作初值，onLayout 会校正） */
function pct(widthPx: number): number {
  const approxContent =
    typeof window !== "undefined" ? window.innerWidth - 56 : 1384;
  return Math.max(20, Math.min(45, (widthPx / approxContent) * 100));
}
