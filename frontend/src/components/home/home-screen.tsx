"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { BackendStatus } from "@/components/backend-status";
import { buttonPrimary, buttonSecondary, card, errorText, input } from "@/components/ui";
import { useAccount } from "@/components/auth/auth-gate";
import { api, type Lesson, type Profile, type Progress } from "@/lib/api/client";

export function HomeScreen() {
  const { account } = useAccount();

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-2">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-3xl font-semibold tracking-tight">Language Tutor</h1>
          <Link href="/account" className={buttonSecondary} title={account.email}>
            Account
          </Link>
        </div>
        <p className="text-zinc-600 dark:text-zinc-400">
          Practice English through conversation with an AI tutor.
        </p>
        <BackendStatus />
      </header>

      {account.has_profile ? <ProfileLoader /> : <Welcome />}
    </main>
  );
}

function Welcome() {
  return (
    <section className={`${card} flex flex-col gap-3`}>
      <h2 className="text-lg font-medium">Welcome! Let&apos;s set up your profile.</h2>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Tell the tutor your level and what you want to practice. It takes a minute.
      </p>
      <Link href="/onboarding" className={`${buttonPrimary} self-start`}>
        Set up my profile
      </Link>
    </section>
  );
}

function ProfileLoader() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getProfile()
      .then(setProfile)
      .catch(() => setError("Could not load your profile. Try reloading the page."));
  }, []);

  if (error) return <p className={errorText}>{error}</p>;
  if (!profile) return <p className="text-sm text-zinc-500">Loading your profile…</p>;
  return <ProfileHome profile={profile} />;
}

function ProfileHome({ profile }: { profile: Profile }) {
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);

  useEffect(() => {
    // Independent requests: run them in parallel.
    api
      .listLessons()
      // Discarded lessons were never really started, so they are not worth listing.
      .then((all) => setLessons(all.filter((lesson) => lesson.status !== "discarded")))
      .catch(() => setLessons([]));
    api
      .getProgress()
      .then(setProgress)
      .catch(() => setProgress(null));
  }, [profile.id]);

  async function startLesson(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStarting(true);
    setError(null);
    try {
      const lesson = await api.createLesson(topic.trim());
      router.push(`/lesson/${lesson.id}`);
    } catch {
      setError("Could not start the lesson. Try again.");
      setStarting(false);
    }
  }

  return (
    <section className="flex flex-col gap-6">
      <h2 className="text-xl font-medium">Hi, {profile.name}!</h2>

      {progress ? (
        <section className={`${card} flex flex-col gap-2`}>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Your progress
          </h3>
          <p className="whitespace-pre-line text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            {progress.text}
          </p>
        </section>
      ) : null}

      <form onSubmit={startLesson} className={`${card} flex flex-col gap-3`}>
        <label htmlFor="topic" className="font-medium">
          Start a new lesson
        </label>
        <input
          id="topic"
          className={input}
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          placeholder={profile.main_topic}
          maxLength={200}
        />
        <p className="text-xs text-zinc-500">
          Leave empty to practice your main topic: {profile.main_topic}.
        </p>
        {error ? <p className={errorText}>{error}</p> : null}
        <button type="submit" className={`${buttonPrimary} self-start`} disabled={starting}>
          {starting ? "Starting…" : "Start lesson"}
        </button>
      </form>

      {lessons.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-medium text-zinc-500">Your lessons</h3>
          <ul className="flex flex-col gap-2">
            {lessons.map((lesson) => (
              <li key={lesson.id}>
                <Link
                  href={`/lesson/${lesson.id}`}
                  className={`${card} flex items-center justify-between gap-4 hover:border-zinc-400 dark:hover:border-zinc-600`}
                >
                  <span className="min-w-0 truncate">{lesson.topic}</span>
                  <span className="flex shrink-0 items-center gap-3 text-xs text-zinc-500">
                    <LessonStatusBadge status={lesson.status} />
                    {new Date(lesson.created_at).toLocaleDateString()}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function LessonStatusBadge({ status }: { status: Lesson["status"] }) {
  return status === "summarized" ? (
    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
      Completed
    </span>
  ) : (
    <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
      In progress
    </span>
  );
}
