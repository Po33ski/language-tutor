"use client";

import { useState } from "react";

import { buttonPrimary, input } from "@/components/ui";

interface MessageComposerProps {
  disabled: boolean;
  onSend: (content: string) => void;
}

export function MessageComposer({ disabled, onSend }: MessageComposerProps) {
  const [value, setValue] = useState("");
  const canSend = !disabled && value.trim().length > 0;

  function send() {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
  }

  return (
    <form
      className="flex items-end gap-2 border-t border-zinc-200 pt-3 dark:border-zinc-800"
      onSubmit={(event) => {
        event.preventDefault();
        send();
      }}
    >
      <textarea
        className={`${input} max-h-40 resize-none`}
        rows={2}
        value={value}
        maxLength={4000}
        placeholder="Write your answer in English… (Enter to send, Shift+Enter for a new line)"
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            send();
          }
        }}
      />
      <button type="submit" className={buttonPrimary} disabled={!canSend}>
        Send
      </button>
    </form>
  );
}
