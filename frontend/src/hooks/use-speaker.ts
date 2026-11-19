"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api/client";
import { splitSentences } from "@/lib/sentences";

/** A reply read aloud while it is still being written, one sentence at a time. */
export interface SpeechStream {
  /** Queue one complete sentence. It plays after the sentences queued before it. */
  push: (sentence: string) => void;
  /** No more sentences. `text` is the whole reply; its message shows as playing. */
  finish: (text: string) => void;
}

/**
 * Plays text with the tutor's voice, sentence by sentence: the first sentence starts
 * playing as soon as it is synthesized, while the next ones are synthesized behind it.
 * Only one text plays at a time; starting another or calling `stop` cancels it.
 */
export function useSpeaker() {
  const [speakingText, setSpeakingText] = useState<string | null>(null);
  // One audio element for every clip: once the browser allowed it to play, it keeps
  // playing later clips without a new user gesture (matters on iOS).
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  // Ends the wait for the clip that is playing now (used by `stop`).
  const endClipRef = useRef<(() => void) | null>(null);
  // Incremented on every new text and on stop, so work for a cancelled text is dropped.
  const generationRef = useRef(0);

  const releaseClip = useCallback(() => {
    audioRef.current?.pause();
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
    endClipRef.current?.();
    endClipRef.current = null;
  }, []);

  const stop = useCallback(() => {
    generationRef.current += 1;
    releaseClip();
    setSpeakingText(null);
  }, [releaseClip]);

  /** Resolves when the clip ends or is stopped; rejects if the browser blocks playback. */
  const playClip = useCallback(
    async (blob: Blob) => {
      releaseClip();
      audioRef.current ??= new Audio();
      const audio = audioRef.current;
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      const ended = new Promise<void>((resolve) => {
        endClipRef.current = resolve;
        audio.onended = () => resolve();
        audio.onerror = () => resolve();
      });
      audio.src = url;
      await audio.play();
      await ended;
    },
    [releaseClip],
  );

  const startStream = useCallback((): SpeechStream => {
    stop();
    const generation = generationRef.current;
    const isCurrent = () => generation === generationRef.current;
    // Synthesis requests run one after another, so the server always works on the
    // earliest sentence first; playback follows in the same order.
    let synthesis: Promise<unknown> = Promise.resolve();
    let playback: Promise<void> = Promise.resolve();

    return {
      push(sentence) {
        if (!isCurrent() || !sentence.trim()) return;
        const clip = synthesis
          .then(() => (isCurrent() ? api.synthesizeSpeech(sentence) : null))
          .catch(() => null); // a failed sentence is skipped
        synthesis = clip;
        playback = playback.then(async () => {
          const blob = await clip;
          if (!blob || !isCurrent()) return;
          try {
            await playClip(blob);
          } catch {
            // Autoplay blocked (or the clip was cancelled): drop the rest of this text.
            if (isCurrent()) stop();
          }
        });
      },
      finish(text) {
        if (!isCurrent()) return;
        setSpeakingText(text);
        playback = playback.then(() => {
          if (isCurrent()) {
            releaseClip();
            setSpeakingText(null);
          }
        });
      },
    };
  }, [playClip, releaseClip, stop]);

  /** Reads a finished text aloud (e.g. the replay button). */
  const speak = useCallback(
    (text: string) => {
      const stream = startStream();
      for (const sentence of splitSentences(text)) stream.push(sentence);
      stream.finish(text);
    },
    [startStream],
  );

  useEffect(() => stop, [stop]);

  return { speak, startStream, stop, speakingText };
}
