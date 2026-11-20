"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";

import {
  ChevronLeftIcon,
  CloseIcon,
  NotesIcon,
  SpeakerIcon,
  SpeakerOffIcon,
} from "@/components/icons";
import { FeedbackPanel } from "@/components/lesson/feedback-panel";
import { LessonSummaryCard } from "@/components/lesson/lesson-summary-card";
import { MessageComposer } from "@/components/lesson/message-composer";
import { MessageList } from "@/components/lesson/message-list";
import { buttonPrimary, buttonSecondary, errorText, iconButton } from "@/components/ui";
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
  const [notesOpen, setNotesOpen] = useState(false);
  // How many notes (corrections + words) the learner has seen in the mobile notes sheet.
  const [seenNotes, setSeenNotes] = useState(0);
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
        // Notes from before this page load are not news.
        setSeenNotes(detail.mistakes.length + detail.vocabulary.length);
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

  const noteCount = mistakes.length + vocabulary.length;

  function openNotes() {
    setSeenNotes(noteCount);
    setNotesOpen(true);
  }

  const closeNotes = useCallback(() => setNotesOpen(false), []);

  const isActive = lesson?.status === "active";

  return (
    <main className="flex h-dvh flex-col">
      <header className="border-b border-line">
        <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-1 px-2 sm:gap-2 sm:px-4">
          <Link href="/" className={iconButton} aria-label="Back to your lessons">
            <ChevronLeftIcon />
          </Link>
          <div className="flex min-w-0 flex-1 flex-col">
            <h1 className="truncate text-[17px] font-bold leading-tight tracking-[-0.01em]">
              {lesson?.topic ?? "Lesson"}
            </h1>
            <p className="truncate text-sm text-muted">
              {lesson === null
                ? " "
                : isActive
                  ? "Lesson in progress"
                  : lesson.status === "summarized"
                    ? "Lesson completed"
                    : "Lesson ended"}
            </p>
          </div>
          <button
            type="button"
            className={`${iconButton} sm:w-auto sm:gap-2 sm:px-3.5 sm:text-[15px] sm:font-semibold`}
            onClick={toggleVoice}
            aria-pressed={voiceEnabled}
            aria-label={voiceEnabled ? "Voice on" : "Voice off"}
            title="Read the tutor's replies aloud"
          >
            {voiceEnabled ? <SpeakerIcon /> : <SpeakerOffIcon className="size-5 text-muted" />}
            <span className="hidden sm:inline">{voiceEnabled ? "Voice on" : "Voice off"}</span>
          </button>
          <button
            type="button"
            className={`${iconButton} relative lg:hidden`}
            onClick={openNotes}
            aria-label={`Corrections and vocabulary (${noteCount})`}
          >
            <NotesIcon />
            {noteCount > seenNotes ? (
              <span className="absolute right-2 top-2 size-2.5 rounded-full bg-fern ring-2 ring-paper" />
            ) : null}
          </button>
          {isActive ? (
            <button
              type="button"
              className={`${buttonSecondary} min-h-10 px-3.5 text-sm sm:px-4`}
              onClick={endLesson}
              disabled={draft !== null || ending}
              aria-label={ending ? "Summarizing…" : "End lesson"}
            >
              {/* Short label on phones, so the lesson title keeps some room. */}
              {ending ? (
                "Summarizing…"
              ) : (
                <>
                  <span className="sm:hidden" aria-hidden>
                    End
                  </span>
                  <span className="hidden sm:inline" aria-hidden>
                    End lesson
                  </span>
                </>
              )}
            </button>
          ) : null}
        </div>
      </header>

      <div className="mx-auto grid min-h-0 w-full max-w-6xl flex-1 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="flex min-h-0 flex-col" aria-busy={draft !== null}>
          <MessageList
            messages={messages}
            draft={draft}
            speakingText={speakingText}
            onPlay={speak}
            onStop={stopSpeaking}
            scrollKey={`${ending}-${lesson?.status}`}
          >
            {ending ? (
              <p className="rounded-3xl bg-surface p-5 text-muted" role="status">
                Writing your lesson summary…
              </p>
            ) : lesson?.summary ? (
              <LessonSummaryCard summary={lesson.summary} />
            ) : null}
          </MessageList>
          {error ? (
            <p className={`${errorText} mx-auto w-full max-w-2xl px-4 pb-2 sm:px-6`} role="alert">
              {error}
            </p>
          ) : null}
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
        <aside className="hidden min-h-0 overflow-y-auto border-l border-line lg:block">
          <FeedbackPanel mistakes={mistakes} vocabulary={vocabulary} />
        </aside>
      </div>

      <NotesSheet open={notesOpen} onClose={closeNotes}>
        <FeedbackPanel mistakes={mistakes} vocabulary={vocabulary} />
      </NotesSheet>
    </main>
  );
}

/** Corrections and vocabulary on small screens: a bottom sheet over the conversation. */
function NotesSheet({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  // On wide screens the notes have their own column and the sheet is hidden; an open
  // modal dialog would still block the page, so close it when the window gets wide.
  useEffect(() => {
    if (!open) return;
    const wide = window.matchMedia("(min-width: 64rem)");
    const closeIfWide = () => {
      if (wide.matches) onClose();
    };
    closeIfWide();
    wide.addEventListener("change", closeIfWide);
    return () => wide.removeEventListener("change", closeIfWide);
  }, [open, onClose]);

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      // A click on the backdrop lands on the dialog element itself.
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      aria-labelledby="notes-title"
      className="mb-0 mt-auto max-h-[85dvh] w-full max-w-none rounded-t-3xl bg-paper text-ink backdrop:bg-black/40 lg:hidden"
    >
      <div className="sticky top-0 flex items-center justify-between border-b border-line bg-paper py-2 pl-5 pr-2">
        <h2 id="notes-title" className="text-[17px] font-bold">
          Your notes
        </h2>
        <button type="button" className={iconButton} onClick={onClose} aria-label="Close">
          <CloseIcon />
        </button>
      </div>
      <div className="pb-[env(safe-area-inset-bottom)]">{children}</div>
    </dialog>
  );
}

function LessonEndedNote({ discarded }: { discarded: boolean }) {
  return (
    <div className="border-t border-line lg:border-t-0">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-3 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p className="text-muted">
          {discarded
            ? "This lesson ended before you wrote anything, so there is no summary."
            : "This lesson has ended. Its summary is saved for your next lessons."}
        </p>
        <Link href="/" className={`${buttonPrimary} shrink-0`}>
          Start a new lesson
        </Link>
      </div>
    </div>
  );
}
