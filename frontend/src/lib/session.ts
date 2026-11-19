"use client";

import { createStoredValue } from "@/lib/stored-value";

// The session token from sign-up or sign-in, sent as "Authorization: Bearer <token>".
// It lives in localStorage rather than a cookie because the API is on another site,
// where cookies count as third-party and Safari blocks them.
const sessionToken = createStoredValue("language-tutor:v1:session-token");

export const readSessionToken = sessionToken.read;
export const setSessionToken = sessionToken.write;

/** The stored session token; `null` on the server and when signed out. */
export const useSessionToken = sessionToken.useValue;

/** Values stored by versions before accounts existed. */
export function forgetLegacyStorage(): void {
  try {
    localStorage.removeItem("language-tutor:v1:access-key");
    localStorage.removeItem("language-tutor:v1:current-user-id");
  } catch {
    // Storage unavailable: nothing to clean up.
  }
}
