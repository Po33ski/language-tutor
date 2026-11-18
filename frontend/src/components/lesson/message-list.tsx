"use client";

import { useEffect, useRef } from "react";

import type { ChatMessage } from "@/lib/api/client";

interface MessageListProps {
  messages: ChatMessage[];
  /** The tutor reply being streamed: "" while waiting for the first token, null when idle. */
  draft: string | null;
  /** Text currently being read aloud (or prepared), if any. */
  speakingText: string | null;
  onPlay: (text: string) => void;
  onStop: () => void;
}

export function MessageList({ messages, draft, speakingText, onPlay, onStop }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, draft]);

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto py-4" aria-live="polite">
      {messages.map((message, index) =>
        message.role === "assistant" ? (
          <div key={index} className="flex max-w-[85%] items-end gap-2 self-start">
            <MessageBubble role="assistant" content={message.content} />
            <PlayButton
              speaking={speakingText === message.content}
              onPlay={() => onPlay(message.content)}
              onStop={onStop}
            />
          </div>
        ) : (
          <MessageBubble key={index} role="user" content={message.content} />
        ),
      )}
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
      className={`whitespace-pre-wrap rounded-2xl px-4 py-2 text-[15px] leading-relaxed ${
        isUser
          ? "max-w-[85%] self-end rounded-br-sm bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
          : "self-start rounded-bl-sm bg-zinc-100 dark:bg-zinc-800"
      }`}
    >
      {content}
    </div>
  );
}

function PlayButton({
  speaking,
  onPlay,
  onStop,
}: {
  speaking: boolean;
  onPlay: () => void;
  onStop: () => void;
}) {
  return (
    <button
      type="button"
      onClick={speaking ? onStop : onPlay}
      className="mb-1 shrink-0 rounded-full p-1.5 text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
      aria-label={speaking ? "Stop reading" : "Read aloud"}
      title={speaking ? "Stop reading" : "Read aloud"}
    >
      {speaking ? <StopIcon /> : <SpeakerIcon />}
    </button>
  );
}

function SpeakerIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <path d="M11 5 6 9H2v6h4l5 4V5Z" />
      <path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor" aria-hidden>
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}
