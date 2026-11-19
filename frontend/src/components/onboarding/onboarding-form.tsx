"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { buttonPrimary, buttonSecondary, card, errorText, input } from "@/components/ui";
import { useAccount } from "@/components/auth/auth-gate";
import { api, type EnglishLevel } from "@/lib/api/client";

const LEVELS: { value: EnglishLevel; label: string }[] = [
  { value: "A1", label: "A1 — Beginner" },
  { value: "A2", label: "A2 — Elementary" },
  { value: "B1", label: "B1 — Intermediate" },
  { value: "B2", label: "B2 — Upper intermediate" },
  { value: "C1", label: "C1 — Advanced" },
  { value: "C2", label: "C2 — Proficient" },
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
      <div className={`${card} flex flex-col gap-3 text-sm`}>
        <p>Your profile is already set up.</p>
        <Link href="/" className={`${buttonSecondary} self-start`}>
          Go to your lessons
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className={`${card} flex flex-col gap-5`}>
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

      <Field label="Your English level" htmlFor="level">
        <select
          id="level"
          className={input}
          value={level}
          onChange={(event) => setLevel(event.target.value as EnglishLevel)}
        >
          {LEVELS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </Field>

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
          {TOPIC_SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => setMainTopic(suggestion)}
              className="rounded-full border border-zinc-300 px-3 py-1 text-xs hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </Field>

      <Field label="Your goal (optional)" htmlFor="goal">
        <textarea
          id="goal"
          className={input}
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
          className={input}
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          maxLength={500}
          rows={2}
          placeholder="e.g. Correct every mistake, use British English"
        />
      </Field>

      {error ? <p className={errorText}>{error}</p> : null}
      <button type="submit" className={`${buttonPrimary} self-start`} disabled={saving}>
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
    <div className="flex flex-col gap-2">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
    </div>
  );
}
