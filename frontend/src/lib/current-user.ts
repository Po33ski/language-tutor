"use client";

import { createStoredValue } from "@/lib/stored-value";

// Versioned keys, so the stored shape can change later without breaking old browsers.
const currentUser = createStoredValue("language-tutor:v1:current-user-id");

export const setCurrentUserId = currentUser.write;

/** The selected profile id; `null` on the server and when none is selected. */
export const useCurrentUserId = currentUser.useValue;
