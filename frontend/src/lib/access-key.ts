"use client";

import { createStoredValue } from "@/lib/stored-value";

// The backend's shared ACCESS_KEY, entered once by the user. A deployed backend rejects
// requests without it; a local one usually has no key configured.
const accessKey = createStoredValue("language-tutor:v1:access-key");

export const readAccessKey = accessKey.read;
export const setAccessKey = accessKey.write;

/** The stored access key; `null` on the server and when none is stored. */
export const useAccessKey = accessKey.useValue;
