"use client";

import { useState } from "react";

import { buttonPrimary, buttonSecondary, errorText, input } from "@/components/ui";
import { useRecorder } from "@/hooks/use-recorder";
import { api } from "@/lib/api/client";

interface MessageComposerProps {
  disabled: boolean;
  onSend: (content: string) => void;
  /** Called when the microphone starts, e.g. to stop the tutor's voice. */
  onRecordingStart: () => void;
}

export function MessageComposer({ disabled, onSend, onRecordingStart }: MessageComposerProps) {
  const [value, setValue] = useState("");
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const { recording, start, stop } = useRecorder();
  const canSend = !disabled && !recording && !transcribing && value.trim().length > 0;

  function send() {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
  }

  async function toggleRecording() {
    setVoiceError(null);
    if (!recording) {
      onRecordingStart();
      try {
        await start();
      } catch {
        setVoiceError("Microphone is not available. Check the browser's permission.");
      }
      return;
    }

    const audio = await stop();
    setTranscribing(true);
    try {
      const text = await api.transcribe(audio);
      if (text) {
        // Spoken answers go straight to the tutor, like in a real conversation.
        onSend(text);
      } else {
        setVoiceError("I didn't catch that. Try again a bit louder.");
      }
    } catch {
      setVoiceError("Could not understand the recording. Try again.");
    } finally {
      setTranscribing(false);
    }
  }

  return (
    <div className="flex flex-col gap-2 border-t border-zinc-200 pt-3 dark:border-zinc-800">
      {voiceError ? <p className={errorText}>{voiceError}</p> : null}
      <form
        className="flex items-end gap-2"
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
          placeholder={
            recording
              ? "Listening… click Stop when you finish speaking."
              : "Speak or write your answer in English… (Enter to send)"
          }
          disabled={recording || transcribing}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              send();
            }
          }}
        />
        {/* Actions on the right, where development overlays never cover them. */}
        <MicButton
          recording={recording}
          transcribing={transcribing}
          // A recording in progress can always be stopped, even if the tutor started typing.
          disabled={!recording && (disabled || transcribing)}
          onClick={toggleRecording}
        />
        <button type="submit" className={buttonPrimary} disabled={!canSend}>
          Send
        </button>
      </form>
    </div>
  );
}

function MicButton({
  recording,
  transcribing,
  disabled,
  onClick,
}: {
  recording: boolean;
  transcribing: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  const label = recording ? "Stop" : transcribing ? "Transcribing…" : "Speak";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={recording}
      className={
        recording
          ? "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-500"
          : `${buttonSecondary} shrink-0 gap-2`
      }
    >
      {recording ? (
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-white" aria-hidden />
      ) : (
        <MicIcon />
      )}
      {label}
    </button>
  );
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
      <rect x="9" y="3" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}
