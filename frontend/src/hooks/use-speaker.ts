"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api/client";

/** Plays text with the tutor's voice. Only one text plays at a time. */
export function useSpeaker() {
  const [speakingText, setSpeakingText] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  // Incremented on every speak/stop, so a slow synthesis request that was superseded
  // does not start playing.
  const generationRef = useRef(0);

  const release = useCallback(() => {
    audioRef.current?.pause();
    audioRef.current = null;
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
  }, []);

  const stop = useCallback(() => {
    generationRef.current += 1;
    release();
    setSpeakingText(null);
  }, [release]);

  const speak = useCallback(
    async (text: string) => {
      release();
      const generation = ++generationRef.current;
      setSpeakingText(text);
      try {
        const blob = await api.synthesizeSpeech(text);
        if (generation !== generationRef.current) return;
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audioRef.current = audio;
        urlRef.current = url;
        audio.onended = () => {
          if (generation === generationRef.current) stop();
        };
        await audio.play();
      } catch {
        // Synthesis failed or the browser blocked autoplay: stay silent.
        if (generation === generationRef.current) stop();
      }
    },
    [release, stop],
  );

  useEffect(() => stop, [stop]);

  return { speak, stop, speakingText };
}
