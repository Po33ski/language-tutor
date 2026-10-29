"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { BackendStatus } from "@/components/backend-status";
import { buttonPrimary, buttonSecondary, card, errorText, input } from "@/components/ui";
import { api, type Lesson, type Profile } from "@/lib/api/client";
import { setCurrentUserId, useCurrentUserId } from "@/lib/current-user";

export function HomeScreen() {
  const [profiles, setProfiles] = useState<Profile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const storedUserId = useCurrentUserId();

  useEffect(() => {
    api
      .listProfiles()
      .then(setProfiles)
      .catch(() => setError("Could not load profiles. Is the backend running?"));
  }, []);

  // A stored id may point to a profile that no longer exists.
  const currentProfile = profiles?.find((profile) => profile.id === storedUserId) ?? null;

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-8 px-4 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Language Tutor</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Practice English through conversation with an AI tutor.
        </p>
        <BackendStatus />
      </header>

      {error ? <p className={errorText}>{error}</p> : null}

      {profiles === null && !error ? (
        <p className="text-sm text-zinc-500">Loading profiles…</p>
      ) : null}

      {profiles !== null && currentProfile === null ? (
        <ProfilePicker profiles={profiles} />
      ) : null}

      {currentProfile !== null ? <ProfileHome profile={currentProfile} /> : null}
    </main>
  );
}

function ProfilePicker({ profiles }: { profiles: Profile[] }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-medium">
        {profiles.length > 0 ? "Who is learning today?" : "Welcome! Let's set up your profile."}
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {profiles.map((profile) => (
          <button
            key={profile.id}
            type="button"
            onClick={() => setCurrentUserId(profile.id)}
            className={`${card} text-left transition-colors hover:border-zinc-400 dark:hover:border-zinc-600`}
          >
            <span className="block font-medium">{profile.name}</span>
            <span className="block text-sm text-zinc-500">
              {profile.level} · {profile.main_topic}
            </span>
          </button>
        ))}
      </div>
      <Link href="/onboarding" className={`${buttonSecondary} self-start`}>
        Create a new profile
      </Link>
    </section>
  );
}

function ProfileHome({ profile }: { profile: Profile }) {
  const router = useRouter();
  const [topic, setTopic] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);

  useEffect(() => {
    api
      .listLessons(profile.id)
      .then(setLessons)
      .catch(() => setLessons([]));
  }, [profile.id]);

  async function startLesson(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStarting(true);
    setError(null);
    try {
      const lesson = await api.createLesson(profile.id, topic.trim());
      router.push(`/lesson/${lesson.id}`);
    } catch {
      setError("Could not start the lesson. Try again.");
      setStarting(false);
    }
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-xl font-medium">Hi, {profile.name}!</h2>
        <button type="button" className={buttonSecondary} onClick={() => setCurrentUserId(null)}>
          Switch profile
        </button>
      </div>

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
                  <span>{lesson.topic}</span>
                  <span className="shrink-0 text-xs text-zinc-500">
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
