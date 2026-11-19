import { readSessionToken, setSessionToken } from "@/lib/session";

import type { components } from "./schema";

type Schemas = components["schemas"];
export type Profile = Schemas["Profile"];
export type ProfileCreate = Schemas["ProfileCreate"];
export type Lesson = Schemas["Lesson"];
export type LessonDetail = Schemas["LessonDetail"];
export type ChatMessage = Schemas["ChatMessage"];
export type Mistake = Schemas["Mistake"];
export type VocabularyItem = Schemas["VocabularyItem"];
export type EnglishLevel = Schemas["EnglishLevel"];
export type LessonSummary = Schemas["LessonSummary"];
export type Progress = Schemas["Progress"];
export type Account = Schemas["Account"];
export type AuthResponse = Schemas["AuthResponse"];

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** `fetch` against the backend, with the session token attached. */
async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = readSessionToken();
  const response = await fetch(`${API_URL}/api${path}`, {
    ...init,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init?.headers },
  });
  // The session expired or was ended elsewhere: forget it, so the sign-in screen shows.
  if (response.status === 401 && token) setSessionToken(null);
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw await errorFrom(response, response.statusText);
  return response.json() as Promise<T>;
}

/** An ApiError with the backend's message (`detail`) when it sent a readable one. */
async function errorFrom(response: Response, fallback: string): Promise<ApiError> {
  const body = await response.json().catch(() => null);
  const detail = body?.detail;
  // Validation errors come as a list: [{ msg: "value is not a valid email address: …" }].
  const message =
    typeof detail === "string"
      ? detail
      : Array.isArray(detail) && typeof detail[0]?.msg === "string"
        ? detail[0].msg
        : fallback;
  return new ApiError(response.status, message);
}

export const api = {
  getHealth: (signal?: AbortSignal) => request<{ status: string }>("/health", { signal }),

  signUp: (email: string, password: string) =>
    request<AuthResponse>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  signIn: (email: string, password: string) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  signOut: async () => {
    await apiFetch("/auth/logout", { method: "POST" });
  },
  getAccount: (signal?: AbortSignal) => request<Account>("/auth/me", { signal }),
  changePassword: async (currentPassword: string, newPassword: string) => {
    const response = await apiFetch("/auth/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    if (!response.ok) throw await errorFrom(response, "Could not change the password.");
  },

  getProfile: () => request<Profile>("/profile"),
  createProfile: (data: ProfileCreate) =>
    request<Profile>("/profile", { method: "POST", body: JSON.stringify(data) }),
  getProgress: () => request<Progress | null>("/profile/progress"),
  listLessons: () => request<Lesson[]>("/lessons"),
  getLesson: (lessonId: string) => request<LessonDetail>(`/lessons/${lessonId}`),
  endLesson: (lessonId: string) =>
    request<Lesson>(`/lessons/${lessonId}/end`, { method: "POST" }),
  createLesson: (topic?: string) =>
    request<Lesson>("/lessons", {
      method: "POST",
      body: JSON.stringify({ topic: topic || null }),
    }),

  /** Speech to text (Whisper). */
  transcribe: async (audio: Blob): Promise<string> => {
    const form = new FormData();
    form.append("audio", audio, "answer");
    // No JSON Content-Type here: the browser sets the multipart boundary itself.
    const response = await apiFetch("/speech/transcribe", {
      method: "POST",
      body: form,
    });
    if (!response.ok) throw new ApiError(response.status, "Could not transcribe the recording.");
    const body: Schemas["TranscriptionResponse"] = await response.json();
    return body.text;
  },

  /** Text to speech (Kokoro); resolves with a WAV file. */
  synthesizeSpeech: async (text: string): Promise<Blob> => {
    const response = await apiFetch("/speech/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) throw new ApiError(response.status, "Could not generate speech.");
    return response.blob();
  },
};

export interface TutorTurnHandlers {
  onToken: (text: string) => void;
  onMistake: (mistake: Mistake) => void;
  onVocabulary: (item: VocabularyItem) => void;
}

/**
 * Runs one tutor turn and streams its server-sent events to the handlers.
 * `content: null` starts the lesson (the tutor speaks first).
 */
export async function streamTutorTurn(
  lessonId: string,
  content: string | null,
  handlers: TutorTurnHandlers,
): Promise<void> {
  const response = await apiFetch(`/lessons/${lessonId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.detail ?? "The tutor could not answer.");
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += value;
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      handleEvent(buffer.slice(0, boundary), handlers);
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

function handleEvent(block: string, handlers: TutorTurnHandlers): void {
  let event = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7);
    else if (line.startsWith("data: ")) data = line.slice(6);
  }
  const payload = data ? JSON.parse(data) : {};
  switch (event) {
    case "token":
      handlers.onToken(payload.text);
      break;
    case "mistake":
      handlers.onMistake(payload);
      break;
    case "vocabulary":
      handlers.onVocabulary(payload);
      break;
    case "error":
      throw new ApiError(500, payload.message);
  }
}
