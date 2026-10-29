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

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : response.statusText;
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  getHealth: (signal?: AbortSignal) => request<{ status: string }>("/health", { signal }),
  listProfiles: () => request<Profile[]>("/profiles"),
  getProfile: (userId: string) => request<Profile>(`/profiles/${userId}`),
  createProfile: (data: ProfileCreate) =>
    request<Profile>("/profiles", { method: "POST", body: JSON.stringify(data) }),
  listLessons: (userId: string) =>
    request<Lesson[]>(`/lessons?user_id=${encodeURIComponent(userId)}`),
  getLesson: (lessonId: string) => request<LessonDetail>(`/lessons/${lessonId}`),
  createLesson: (userId: string, topic?: string) =>
    request<Lesson>("/lessons", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, topic: topic || null }),
    }),
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
  const response = await fetch(`${API_URL}/api/lessons/${lessonId}/messages`, {
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
