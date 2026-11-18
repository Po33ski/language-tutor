"use client";

import { useSyncExternalStore } from "react";

/**
 * A string kept in localStorage that components can subscribe to.
 * Reads and writes never throw: without storage (e.g. private mode) the value lives
 * only for the current page view.
 */
export function createStoredValue(key: string) {
  const listeners = new Set<() => void>();
  let fallback: string | null = null;

  function read(): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return fallback;
    }
  }

  function write(value: string | null): void {
    fallback = value;
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch {
      // Storage unavailable: keep the in-memory fallback.
    }
    listeners.forEach((listener) => listener());
  }

  function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  /** The stored value; `null` on the server and when nothing is stored. */
  function useValue(): string | null {
    return useSyncExternalStore(subscribe, read, () => null);
  }

  return { useValue, read, write };
}
