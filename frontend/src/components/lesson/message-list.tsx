"use client";

import { useEffect, useRef } from "react";

import type { ChatMessage } from "@/lib/api/client";

interface MessageListProps {
  messages: ChatMessage[];
  /** The tutor reply being streamed: "" while waiting for the first token, null when idle. */
  draft: string | null;
}

export function MessageList({ messages, draft }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, draft]);

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto py-4" aria-live="polite">
      {messages.map((message, index) => (
        <MessageBubble key={index} role={message.role} content={message.content} />
      ))}
      {draft !== null ? (
        draft ? (
          <MessageBubble role="assistant" content={draft} />
        ) : (
          <p className="text-sm text-zinc-500">Tutor is typing…</p>
        )
      ) : null}
      <div ref={bottomRef} />
    </div>
  );
}

function MessageBubble({ role, content }: ChatMessage) {
  const isUser = role === "user";
  return (
    <div
      className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-[15px] leading-relaxed ${
        isUser
          ? "self-end rounded-br-sm bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
          : "self-start rounded-bl-sm bg-zinc-100 dark:bg-zinc-800"
      }`}
    >
      {content}
    </div>
  );
}
