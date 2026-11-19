"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { FeedbackPanel } from "@/components/lesson/feedback-panel";
import { LessonSummaryCard } from "@/components/lesson/lesson-summary-card";
import { MessageComposer } from "@/components/lesson/message-composer";
import { MessageList } from "@/components/lesson/message-list";
import { buttonSecondary, card, errorText } from "@/components/ui";
import { useSpeaker } from "@/hooks/use-speaker";
import {
  api,
  ApiError,
  streamTutorTurn,
  type ChatMessage,
  type Lesson,
  type Mistake,
  type VocabularyItem,
} from "@/lib/api/client";
import { takeSentences } from "@/lib/sentences";
import { setVoiceEnabled, useVoiceEnabled } from "@/lib/voice-settings";

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
  const [ending, setEnding] = useState(false);
  const voiceEnabled = useVoiceEnabled();
  const { speak, startStream, stop: stopSpeaking, speakingText } = useSpeaker();

  // Read through a ref so toggling the voice does not recreate `runTurn` (which would
  // re-run the lesson loading effect).
  const voiceEnabledRef = useRef(voiceEnabled);
  useEffect(() => {
    voiceEnabledRef.current = voiceEnabled;
  }, [voiceEnabled]);

  const runTurn = useCallback(
    async (content: string | null) => {
      setError(null);
      setDraft("");
      let reply = "";
      // Read the reply aloud while it streams: each finished sentence is queued at once.
      const voice = voiceEnabledRef.current ? startStream() : null;
      let unspoken = "";
      try {
        await streamTutorTurn(lessonId, content, {
          onToken: (text) => {
            reply += text;
            setDraft(reply);
            if (voice) {
              const { sentences, rest } = takeSentences(unspoken + text);
              sentences.forEach(voice.push);
              unspoken = rest;
            }
          },
          onMistake: (mistake) => setMistakes((previous) => [...previous, mistake]),
          onVocabulary: (item) => setVocabulary((previous) => [...previous, item]),
        });
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : "The tutor could not answer.");
      } finally {
        if (reply) setMessages((previous) => [...previous, { role: "assistant", content: reply }]);
        setDraft(null);
        if (voice) {
          voice.push(unspoken);
          voice.finish(reply);
        }
      }
    },
    [lessonId, startStream],
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

  async function endLesson() {
    if (!window.confirm("End this lesson? The tutor will write a summary of it.")) return;
    setEnding(true);
    setError(null);
    try {
      setLesson(await api.endLesson(lessonId));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not end the lesson.");
    } finally {
      setEnding(false);
    }
  }

  function toggleVoice() {
    if (voiceEnabled) stopSpeaking();
    setVoiceEnabled(!voiceEnabled);
  }

  const isActive = lesson?.status === "active";

  return (
    <main className="mx-auto flex h-dvh w-full max-w-6xl flex-col gap-4 px-4 py-4">
      <header className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <Link href="/" className="text-sm text-zinc-500 hover:underline">
            ← Back
          </Link>
          <h1 className="truncate text-xl font-semibold">{lesson?.topic ?? "Lesson"}</h1>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            className={buttonSecondary}
            onClick={toggleVoice}
            aria-pressed={voiceEnabled}
            title="Read the tutor's replies aloud"
          >
            {voiceEnabled ? "Voice on" : "Voice off"}
          </button>
          {isActive ? (
            <button
              type="button"
              className={buttonSecondary}
              onClick={endLesson}
              disabled={draft !== null || ending}
            >
              {ending ? "Summarizing…" : "End lesson"}
            </button>
          ) : null}
        </div>
      </header>

      <div className="grid min-h-0 flex-1 gap-6 lg:grid-cols-[1fr_320px]">
        <section className="flex min-h-0 flex-col" aria-busy={draft !== null}>
          <MessageList
            messages={messages}
            draft={draft}
            speakingText={speakingText}
            onPlay={speak}
            onStop={stopSpeaking}
          />
          {error ? <p className={`${errorText} pb-2`}>{error}</p> : null}
          {lesson && !isActive ? (
            <LessonEndedNote discarded={lesson.status === "discarded"} />
          ) : (
            <MessageComposer
              disabled={draft !== null || ending || !lesson}
              onSend={send}
              onRecordingStart={stopSpeaking}
            />
          )}
        </section>
        <aside className="flex min-h-0 flex-col gap-6 overflow-y-auto">
          {ending ? (
            <p className={`${card} text-sm text-zinc-500`}>Summarizing your lesson…</p>
          ) : null}
          {lesson?.summary ? <LessonSummaryCard summary={lesson.summary} /> : null}
          <FeedbackPanel mistakes={mistakes} vocabulary={vocabulary} />
        </aside>
      </div>
    </main>
  );
}

function LessonEndedNote({ discarded }: { discarded: boolean }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-200 pt-3 text-sm text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
      <span>
        {discarded
          ? "This lesson ended before you wrote anything, so there is no summary."
          : "This lesson has ended. Your summary is saved for future lessons."}
      </span>
      <Link href="/" className={buttonSecondary}>
        Start a new lesson
      </Link>
    </div>
  );
}
