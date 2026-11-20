"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { buttonPrimary, buttonSecondary, errorText, fieldLabel, input, panel } from "@/components/ui";
import { useAccount } from "@/components/auth/auth-gate";
import { api, type EnglishLevel } from "@/lib/api/client";

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

export function OnboardingForm() {
  const router = useRouter();
  const { account, refresh } = useAccount();
  const [name, setName] = useState("");
  const [level, setLevel] = useState<EnglishLevel>("B1");
  const [mainTopic, setMainTopic] = useState("");
  const [goal, setGoal] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.createProfile({
        name: name.trim(),
        level,
        main_topic: mainTopic.trim(),
        goal: goal.trim(),
        preferences: notes.trim() ? { notes: notes.trim() } : {},
      });
      // The home screen reads `has_profile` from the account: update it before going there.
      await refresh();
      router.push("/");
    } catch {
      setError("Could not save the profile. Try again.");
      setSaving(false);
    }
  }

  // `saving` stays true after a successful submit, while the page moves home.
  if (account.has_profile && !saving) {
    return (
      <div className={`${panel} flex flex-col items-start gap-4`}>
        <p>Your profile is already set up.</p>
        <Link href="/" className={buttonSecondary}>
          Go to your lessons
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-8">
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
            <label
              key={option.value}
              className="group flex cursor-pointer flex-col rounded-xl border border-line px-3.5 py-3 transition-colors hover:bg-surface has-checked:border-ink has-checked:bg-ink has-checked:text-paper has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-fern"
            >
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
                onClick={() => setMainTopic(suggestion)}
                aria-pressed={selected}
                className={`min-h-9 rounded-full border px-3.5 text-sm transition-colors ${
                  selected
                    ? "border-ink bg-ink text-paper"
                    : "border-line hover:bg-surface"
                }`}
              >
                {suggestion}
              </button>
            );
          })}
        </div>
      </Field>

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

      {error ? <p className={errorText}>{error}</p> : null}
      <button type="submit" className={`${buttonPrimary} w-full sm:w-auto sm:self-start`} disabled={saving}>
        {saving ? "Saving…" : "Create profile"}
      </button>
    </form>
  );
}

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
