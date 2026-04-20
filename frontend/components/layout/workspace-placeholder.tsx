import { MessageSquareIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * Phase 0 的占位 workspace 组件——每个路由页面只显示标题 + 描述，
 * 证明 WorkspaceShell 复用 + 路由切换 OK。
 * Phase 1/2 逐步替换为真实内容。
 */
export function WorkspacePlaceholder({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{description}</p>
      </div>

      <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        <p>Phase 0：仅布局壳</p>
        <div className="mt-1 flex flex-wrap items-center justify-center gap-x-1 gap-y-2">
          <span>打开右侧</span>
          <ChatHintButton />
          <span>试试 demo artifact · 按</span>
          <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs">
            ⌘K
          </kbd>
          <span>打开命令面板</span>
        </div>
      </div>
    </div>
  );
}

function ChatHintButton() {
  return (
    <Button
      variant="ghost"
      size="xs"
      className="gap-1 align-baseline"
      disabled
    >
      <MessageSquareIcon className="size-3" />
      Chat
    </Button>
  );
}
