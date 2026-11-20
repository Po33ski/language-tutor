"use client";

import { useState } from "react";

import { CloseIcon } from "@/components/icons";
import { buttonPrimary, errorText, fieldLabel, hint, input } from "@/components/ui";
import { ApiError, type EnglishLevel, type Profile, type ProfileCreate } from "@/lib/api/client";

const LEVELS: { value: EnglishLevel; label: string }[] = [
  { value: "A1", label: "Beginner" },
  { value: "A2", label: "Elementary" },
  { value: "B1", label: "Intermediate" },
  { value: "B2", label: "Upper intermediate" },
  { value: "C1", label: "Advanced" },
  { value: "C2", label: "Proficient" },
];

const TOPIC_SUGGESTIONS = [
  "Job interview preparation",
  "Business meetings",
  "Travel and everyday situations",
  "Small talk",
  "Presentations",
];

// Matches the backend limits (5–30 minutes).
const LESSON_LENGTHS = [5, 10, 15, 20, 25, 30];
const DEFAULT_LESSON_MINUTES = 15;

// The form's own free-text preference; every other key was saved by the tutor.
const NOTES_KEY = "notes";

interface ProfileFormProps {
  /** The current profile when editing; the onboarding form starts empty. */
  initial?: Profile;
  submitLabel: string;
  savingLabel: string;
  /** Saves the profile. Throwing shows an error under the form. */
  onSubmit: (data: ProfileCreate) => Promise<void>;
  /** Shown under the button after a successful save (edit mode). */
  savedMessage?: string;
}

/** The learner's main preferences: used by onboarding and by the edit-profile page. */
export function ProfileForm({
  initial,
  submitLabel,
  savingLabel,
  onSubmit,
  savedMessage,
}: ProfileFormProps) {
  const [name, setName] = useState(initial?.name ?? "");
  const [level, setLevel] = useState<EnglishLevel>(initial?.level ?? "B1");
  const [mainTopic, setMainTopic] = useState(initial?.main_topic ?? "");
  const [lessonMinutes, setLessonMinutes] = useState(
    initial?.lesson_minutes ?? DEFAULT_LESSON_MINUTES,
  );
  const [goal, setGoal] = useState(initial?.goal ?? "");
  const [notes, setNotes] = useState(initial?.preferences?.[NOTES_KEY] ?? "");
  const [tutorPreferences, setTutorPreferences] = useState(() =>
    Object.entries(initial?.preferences ?? {}).filter(([key]) => key !== NOTES_KEY),
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setError(null);
    const preferences = Object.fromEntries(tutorPreferences);
    if (notes.trim()) preferences[NOTES_KEY] = notes.trim();
    try {
      await onSubmit({
        name: name.trim(),
        level,
        main_topic: mainTopic.trim(),
        goal: goal.trim(),
        preferences,
        lesson_minutes: lessonMinutes,
      });
      setSaved(true);
    } catch (caught) {
      setError(
        caught instanceof ApiError && caught.status === 422
          ? caught.message
          : "Could not save the profile. Try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} onChange={() => setSaved(false)} className="flex flex-col gap-8">
      <Field label="Your name" htmlFor="name">
        <input
          id="name"
          className={input}
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
          maxLength={50}
          autoComplete="given-name"
        />
      </Field>

      <fieldset>
        <legend className={`${fieldLabel} mb-3`}>Your English level</legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {LEVELS.map((option) => (
            <label key={option.value} className={choiceCard}>
              <input
                type="radio"
                name="level"
                value={option.value}
                checked={level === option.value}
                onChange={() => setLevel(option.value)}
                className="sr-only"
              />
              <span className="text-lg font-bold">{option.value}</span>
              <span className="text-sm text-muted group-has-checked:text-paper/75">
                {option.label}
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <Field label="What do you want to practice?" htmlFor="main-topic">
        <input
          id="main-topic"
          className={input}
          value={mainTopic}
          onChange={(event) => setMainTopic(event.target.value)}
          required
          maxLength={200}
          placeholder="e.g. Job interview preparation"
        />
        <div className="flex flex-wrap gap-2">
          {TOPIC_SUGGESTIONS.map((suggestion) => {
            const selected = mainTopic === suggestion;
            return (
              <button
                key={suggestion}
                type="button"
                onClick={() => {
                  setMainTopic(suggestion);
                  setSaved(false);
                }}
                aria-pressed={selected}
                className={`min-h-9 rounded-full border px-3.5 text-sm transition-colors ${
                  selected ? "border-ink bg-ink text-paper" : "border-line hover:bg-surface"
                }`}
              >
                {suggestion}
              </button>
            );
          })}
        </div>
      </Field>

      <fieldset>
        <legend className={fieldLabel}>How long should a lesson be?</legend>
        <p className={`${hint} mb-3 mt-1`}>
          The tutor paces the conversation to fit and wraps up when time runs out.
        </p>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          {LESSON_LENGTHS.map((minutes) => (
            <label key={minutes} className={`${choiceCard} items-center text-center`}>
              <input
                type="radio"
                name="lesson-minutes"
                value={minutes}
                checked={lessonMinutes === minutes}
                onChange={() => setLessonMinutes(minutes)}
                className="sr-only"
              />
              <span className="text-lg font-bold">{minutes}</span>
              <span className="text-sm text-muted group-has-checked:text-paper/75">min</span>
            </label>
          ))}
        </div>
      </fieldset>

      <Field label="Your goal (optional)" htmlFor="goal">
        <textarea
          id="goal"
          className={`${input} resize-none`}
          value={goal}
          onChange={(event) => setGoal(event.target.value)}
          maxLength={500}
          rows={2}
          placeholder="e.g. Get a job as a software developer in London"
        />
      </Field>

      <Field label="Anything the tutor should know? (optional)" htmlFor="notes">
        <textarea
          id="notes"
          className={`${input} resize-none`}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          maxLength={500}
          rows={2}
          placeholder="e.g. Correct every mistake, use British English"
        />
      </Field>

      {tutorPreferences.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className={fieldLabel}>Saved by your tutor</h2>
          <p className={hint}>
            Things you told the tutor during lessons. Remove any that no longer apply.
          </p>
          <ul className="flex flex-col divide-y divide-line border-y border-line">
            {tutorPreferences.map(([key, value]) => (
              <li key={key} className="flex items-center gap-3 py-2.5">
                <span className="min-w-0 flex-1 text-[15px]">{value}</span>
                <button
                  type="button"
                  className="inline-flex size-9 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface hover:text-ink"
                  aria-label={`Remove: ${value}`}
                  onClick={() => {
                    setTutorPreferences((current) => current.filter(([k]) => k !== key));
                    setSaved(false);
                  }}
                >
                  <CloseIcon className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="flex flex-col gap-3">
        {error ? (
          <p className={errorText} role="alert">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          className={`${buttonPrimary} w-full sm:w-auto sm:self-start`}
          disabled={saving}
        >
          {saving ? savingLabel : submitLabel}
        </button>
        {saved && savedMessage ? (
          <p className="text-sm font-semibold text-fern" role="status">
            {savedMessage}
          </p>
        ) : null}
      </div>
    </form>
  );
}

const choiceCard =
  "group flex cursor-pointer flex-col rounded-xl border border-line px-3.5 py-3 transition-colors hover:bg-surface has-checked:border-ink has-checked:bg-ink has-checked:text-paper has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-fern";

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3">
      <label htmlFor={htmlFor} className={fieldLabel}>
        {label}
      </label>
      {children}
    </div>
  );
}
