"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { SpeakerIcon, StopIcon } from "@/components/icons";
import type { ChatMessage } from "@/lib/api/client";

interface MessageListProps {
  messages: ChatMessage[];
  /** The tutor reply being streamed: "" while waiting for the first token, null when idle. */
  draft: string | null;
  /** Text currently being read aloud (or prepared), if any. */
  speakingText: string | null;
  onPlay: (text: string) => void;
  onStop: () => void;
  /** Shown after the conversation, e.g. the lesson summary. */
  children?: ReactNode;
  /** Changes when `children` changes, so the list scrolls down to show it. */
  scrollKey?: string;
}

export function MessageList({
  messages,
  draft,
  speakingText,
  onPlay,
  onStop,
  children,
  scrollKey,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, draft, scrollKey]);

  return (
    <div className="flex-1 overflow-y-auto" aria-live="polite">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-4 py-6 sm:px-6">
        {messages.map((message, index) =>
          message.role === "assistant" ? (
            <div key={index} className="flex max-w-[88%] items-end gap-1 self-start">
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
            <div className="max-w-[88%] self-start pr-10">
              <MessageBubble role="assistant" content={draft} />
            </div>
          ) : (
            <TypingIndicator />
          )
        ) : null}
        {children}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function MessageBubble({ role, content }: ChatMessage) {
  const isUser = role === "user";
  return (
    <div
      className={`whitespace-pre-wrap break-words rounded-[20px] px-4 py-2.5 text-base leading-relaxed ${
        isUser
          ? "max-w-[85%] self-end rounded-br-md bg-ink text-paper"
          : "self-start rounded-bl-md bg-surface"
      }`}
    >
      {content}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 self-start rounded-[20px] rounded-bl-md bg-surface px-4 py-4">
      <span className="sr-only">The tutor is typing…</span>
      {[0, 160, 320].map((delay) => (
        <span
          key={delay}
          className="size-2 rounded-full bg-muted motion-safe:animate-[typing-dot_1.2s_ease-in-out_infinite]"
          style={{ animationDelay: `${delay}ms` }}
          aria-hidden
        />
      ))}
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
      className={`inline-flex size-9 shrink-0 items-center justify-center rounded-full transition-colors hover:bg-surface ${
        speaking ? "text-fern" : "text-muted hover:text-ink"
      }`}
      aria-label={speaking ? "Stop reading" : "Read aloud"}
      title={speaking ? "Stop reading" : "Read aloud"}
    >
      {speaking ? <StopIcon /> : <SpeakerIcon className="size-[18px]" />}
    </button>
  );
}
