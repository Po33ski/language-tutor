"use client";

import { useState } from "react";

import { MicIcon, SendIcon, StopIcon } from "@/components/icons";
import { errorText } from "@/components/ui";
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
        setVoiceError("The microphone is not available. Allow it in your browser settings.");
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
        setVoiceError("No speech was heard. Try again a bit louder.");
      }
    } catch {
      setVoiceError("The recording could not be understood. Try again.");
    } finally {
      setTranscribing(false);
    }
  }

  return (
    <div className="border-t border-line bg-paper lg:border-t-0">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-2 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 sm:px-6">
        {voiceError ? (
          <p className={`${errorText} px-1`} role="alert">
            {voiceError}
          </p>
        ) : null}
        <form
          className="flex items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            send();
          }}
        >
          <div
            className={`flex min-w-0 flex-1 rounded-[24px] border transition-colors ${
              recording
                ? "border-fern bg-fern-soft"
                : "border-line bg-paper focus-within:border-fern focus-within:ring-3 focus-within:ring-fern/15"
            }`}
          >
            <textarea
              className="block max-h-40 min-h-12 w-full resize-none field-sizing-content bg-transparent px-4 py-3 text-base leading-normal outline-none placeholder:text-muted/80 disabled:cursor-not-allowed"
              rows={1}
              value={value}
              maxLength={4000}
              aria-label="Your answer"
              placeholder={
                recording
                  ? "Listening…"
                  : transcribing
                    ? "Transcribing…"
                    : "Speak or type your answer"
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
          </div>
          {/* Actions on the right, where development overlays never cover them. */}
          <MicButton
            recording={recording}
            transcribing={transcribing}
            // A recording in progress can always be stopped, even if the tutor started typing.
            disabled={!recording && (disabled || transcribing)}
            onClick={toggleRecording}
          />
          <button
            type="submit"
            className="inline-flex size-12 shrink-0 items-center justify-center rounded-full bg-ink text-paper transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-25"
            disabled={!canSend}
            aria-label="Send"
          >
            <SendIcon />
          </button>
        </form>
      </div>
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
      aria-label={label}
      className={`relative inline-flex h-12 min-w-12 shrink-0 items-center justify-center gap-2 rounded-full px-3.5 text-[15px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 sm:px-5 ${
        recording ? "bg-ink text-paper" : "bg-fern text-paper hover:opacity-90"
      }`}
    >
      {recording ? (
        <span
          className="absolute inset-0 rounded-full ring-4 ring-fern/40 motion-safe:animate-pulse"
          aria-hidden
        />
      ) : null}
      {recording ? <StopIcon /> : <MicIcon />}
      <span className="hidden sm:inline" aria-hidden>
        {label}
      </span>
    </button>
  );
}
