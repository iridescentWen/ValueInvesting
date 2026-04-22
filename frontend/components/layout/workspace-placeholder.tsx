"use client";

import { MessageSquareIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n";

export function WorkspacePlaceholder({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  const t = useT();
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{description}</p>
      </div>

      <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        <p>{t("placeholder_page.phase0_note")}</p>
        <div className="mt-1 flex flex-wrap items-center justify-center gap-x-1 gap-y-2">
          <span>{t("placeholder_page.open_right")}</span>
          <ChatHintButton />
          <span>{t("placeholder_page.try_artifact")}</span>
          <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs">
            ⌘K
          </kbd>
          <span>{t("placeholder_page.open_cmd_palette")}</span>
        </div>
      </div>
    </div>
  );
}

function ChatHintButton() {
  const t = useT();
  return (
    <Button
      variant="ghost"
      size="xs"
      className="gap-1 align-baseline"
      disabled
    >
      <MessageSquareIcon className="size-3" />
      {t("chat.header")}
    </Button>
  );
}
