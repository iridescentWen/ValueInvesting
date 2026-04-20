"use client";

import { MessageSquareIcon, SparklesIcon, XIcon } from "lucide-react";

import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
} from "@/components/ai-elements/prompt-input";
import {
  Tool,
  ToolContent,
  ToolHeader,
  ToolInput,
  ToolOutput,
} from "@/components/ai-elements/tool";
import { Button } from "@/components/ui/button";
import type { ChatMessage, ChatToolCall } from "@/lib/chat";
import { useChatStream } from "@/lib/chat";
import { useAppStore } from "@/lib/store";

export function ChatPanel() {
  const open = useAppStore((s) => s.chatPanelOpen);
  const toggle = useAppStore((s) => s.toggleChatPanel);

  if (!open) return <ChatPanelCollapsed onExpand={toggle} />;

  return (
    <div className="flex h-full flex-col border-l bg-background">
      <div className="flex h-12 items-center justify-between border-b px-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <SparklesIcon className="size-4 text-(color:--color-brand)" />
          Chat
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Close chat"
          onClick={toggle}
        >
          <XIcon />
        </Button>
      </div>

      <ChatBody />
    </div>
  );
}

function ChatPanelCollapsed({ onExpand }: { onExpand: () => void }) {
  return (
    <button
      type="button"
      onClick={onExpand}
      aria-label="Open chat"
      className="flex h-full w-10 flex-col items-center justify-start gap-3 border-l bg-sidebar py-3 text-muted-foreground hover:text-foreground"
    >
      <MessageSquareIcon className="size-4" />
      <span
        className="text-xs tracking-wider"
        style={{ writingMode: "vertical-rl" }}
      >
        CHAT
      </span>
    </button>
  );
}

function ChatBody() {
  const { messages, isStreaming, error, send } = useChatStream();

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <Conversation>
        <ConversationContent>
          {messages.length === 0 ? (
            <ConversationEmptyState
              icon={<SparklesIcon className="size-6" />}
              title="问价值投资 AI"
              description="试试「用安全边际评估一下 AAPL」"
            />
          ) : (
            messages.map((m) => <ChatMessageView key={m.id} message={m} />)
          )}
          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <PromptInput
        className="border-t"
        onSubmit={async ({ text }) => {
          if (!text.trim() || isStreaming) return;
          await send(text);
        }}
      >
        <PromptInputTextarea
          placeholder="问点什么……Shift+Enter 换行"
          disabled={isStreaming}
        />
        <PromptInputFooter>
          <span className="text-xs text-muted-foreground">
            {isStreaming ? "思考中…" : ""}
          </span>
          <PromptInputSubmit
            disabled={isStreaming}
            status={isStreaming ? "streaming" : undefined}
          />
        </PromptInputFooter>
      </PromptInput>
    </div>
  );
}

function ChatMessageView({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <Message from="user">
        <MessageContent>
          <div className="whitespace-pre-wrap">{message.content}</div>
        </MessageContent>
      </Message>
    );
  }

  return (
    <Message from="assistant">
      <MessageContent>
        {message.toolCalls.map((t) => (
          <ToolCallView key={t.id} tool={t} />
        ))}
        {message.content && <MessageResponse>{message.content}</MessageResponse>}
      </MessageContent>
    </Message>
  );
}

function ToolCallView({ tool }: { tool: ChatToolCall }) {
  const state =
    tool.result !== undefined ? "output-available" : "input-available";
  return (
    <Tool defaultOpen={false}>
      <ToolHeader type={`tool-${tool.name}`} state={state} title={tool.name} />
      <ToolContent>
        <ToolInput input={tool.args} />
        {tool.result !== undefined && (
          <ToolOutput output={tool.result} errorText={undefined} />
        )}
      </ToolContent>
    </Tool>
  );
}
