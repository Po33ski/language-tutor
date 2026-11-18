"use client";

import { createStoredValue } from "@/lib/stored-value";

const voiceSetting = createStoredValue("language-tutor:v1:voice-enabled");

/** Whether the tutor reads its replies aloud. On by default. */
export function useVoiceEnabled(): boolean {
  return voiceSetting.useValue() !== "off";
}

export function setVoiceEnabled(enabled: boolean): void {
  voiceSetting.write(enabled ? "on" : "off");
}
