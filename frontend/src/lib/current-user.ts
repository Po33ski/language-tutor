"use client";

import { useSyncExternalStore } from "react";

// Versioned key, so the stored shape can change later without breaking old browsers.
const STORAGE_KEY = "language-tutor:v1:current-user-id";
const listeners = new Set<() => void>();

function read(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setCurrentUserId(userId: string | null): void {
  try {
    if (userId) localStorage.setItem(STORAGE_KEY, userId);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable (e.g. private mode): selection lasts only for this page view.
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The selected profile id; `null` on the server and when none is selected. */
export function useCurrentUserId(): string | null {
  return useSyncExternalStore(subscribe, read, () => null);
}
