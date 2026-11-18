"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Preferred first; Safari only supports audio/mp4.
const MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];

/** Records audio from the microphone with MediaRecorder. */
export function useRecorder() {
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const start = useCallback(async () => {
    // Asks for microphone permission on first use; throws if denied.
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.start();
    recorderRef.current = recorder;
    setRecording(true);
  }, []);

  /** Stops recording and resolves with the recorded audio. */
  const stop = useCallback(
    () =>
      new Promise<Blob>((resolve) => {
        const recorder = recorderRef.current;
        if (!recorder) {
          resolve(new Blob());
          return;
        }
        recorder.onstop = () => {
          recorder.stream.getTracks().forEach((track) => track.stop());
          recorderRef.current = null;
          setRecording(false);
          resolve(new Blob(chunksRef.current, { type: recorder.mimeType }));
        };
        recorder.stop();
      }),
    [],
  );

  // Release the microphone if the component unmounts mid-recording.
  useEffect(
    () => () => recorderRef.current?.stream.getTracks().forEach((track) => track.stop()),
    [],
  );

  return { recording, start, stop };
}
