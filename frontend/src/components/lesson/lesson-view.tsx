"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";

import { FeedbackPanel } from "@/components/lesson/feedback-panel";
import { MessageComposer } from "@/components/lesson/message-composer";
import { MessageList } from "@/components/lesson/message-list";
import { errorText } from "@/components/ui";
import {
  api,
  ApiError,
  streamTutorTurn,
  type ChatMessage,
  type Lesson,
  type Mistake,
  type VocabularyItem,
} from "@/lib/api/client";

// Lessons whose opening turn was already requested in this page session. Module-level so
// React's development double-mount does not start the lesson twice.
const kickoffRequested = new Set<string>();

export function LessonView({ params }: { params: Promise<{ id: string }> }) {
  const { id: lessonId } = use(params);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [mistakes, setMistakes] = useState<Mistake[]>([]);
  const [vocabulary, setVocabulary] = useState<VocabularyItem[]>([]);
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runTurn = useCallback(
    async (content: string | null) => {
      setError(null);
      setDraft("");
      let reply = "";
      try {
        await streamTutorTurn(lessonId, content, {
          onToken: (text) => {
            reply += text;
            setDraft(reply);
          },
          onMistake: (mistake) => setMistakes((previous) => [...previous, mistake]),
          onVocabulary: (item) => setVocabulary((previous) => [...previous, item]),
        });
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : "The tutor could not answer.");
      } finally {
        if (reply) setMessages((previous) => [...previous, { role: "assistant", content: reply }]);
        setDraft(null);
      }
    },
    [lessonId],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .getLesson(lessonId)
      .then((detail) => {
        if (cancelled) return;
        setLesson(detail.lesson);
        setMessages(detail.messages);
        setMistakes(detail.mistakes);
        setVocabulary(detail.vocabulary);
        const isNew = detail.messages.length === 0 && detail.lesson.status === "active";
        if (isNew && !kickoffRequested.has(lessonId)) {
          kickoffRequested.add(lessonId);
          void runTurn(null);
        }
      })
      .catch(() => {
        if (!cancelled) setError("Could not load this lesson.");
      });
    return () => {
      cancelled = true;
    };
  }, [lessonId, runTurn]);

  function send(content: string) {
    setMessages((previous) => [...previous, { role: "user", content }]);
    void runTurn(content);
  }

  return (
    <main className="mx-auto flex h-dvh w-full max-w-6xl flex-col gap-4 px-4 py-4">
      <header className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <Link href="/" className="text-sm text-zinc-500 hover:underline">
            ← Back
          </Link>
          <h1 className="truncate text-xl font-semibold">{lesson?.topic ?? "Lesson"}</h1>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 gap-6 lg:grid-cols-[1fr_320px]">
        <section className="flex min-h-0 flex-col" aria-busy={draft !== null}>
          <MessageList messages={messages} draft={draft} />
          {error ? <p className={`${errorText} pb-2`}>{error}</p> : null}
          <MessageComposer
            disabled={draft !== null || lesson?.status !== "active"}
            onSend={send}
          />
        </section>
        <FeedbackPanel mistakes={mistakes} vocabulary={vocabulary} />
      </div>
    </main>
  );
}
