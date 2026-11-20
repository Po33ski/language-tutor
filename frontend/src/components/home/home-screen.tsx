"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppHeader } from "@/components/brand";
import { BackendStatus } from "@/components/backend-status";
import { CheckIcon, ChevronRightIcon, UserIcon } from "@/components/icons";
import {
  buttonPrimary,
  errorText,
  fieldLabel,
  hint,
  iconButton,
  input,
  pageTitle,
  panel,
  sectionTitle,
} from "@/components/ui";
import { useAccount } from "@/components/auth/auth-gate";
import { api, type Lesson, type Profile, type Progress } from "@/lib/api/client";

export function HomeScreen() {
  const { account } = useAccount();

  return (
    <>
      <AppHeader
        action={
          <Link
            href="/account"
            className={`${iconButton} sm:w-auto sm:gap-2 sm:px-4 sm:text-[15px] sm:font-semibold`}
            aria-label="Account"
            title={account.email}
          >
            <UserIcon />
            <span className="hidden sm:inline">Account</span>
          </Link>
        }
      />
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 pb-16 pt-8 sm:px-6 sm:pt-12">
        <BackendStatus />
        {account.has_profile ? <ProfileLoader /> : <Welcome />}
      </main>
    </>
  );
}

function Welcome() {
  return (
    <section className="flex flex-col items-start gap-4">
      <h1 className={pageTitle}>Welcome</h1>
      <p className="max-w-[60ch] text-[17px] leading-relaxed text-muted">
        Set up your profile so the tutor can plan lessons at your level and on the topics
        you need. It takes a minute.
      </p>
      <Link href="/onboarding" className={buttonPrimary}>
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
      .catch(() => setError("Could not load your profile. Reload the page to try again."));
  }, []);

  if (error) return <p className={errorText}>{error}</p>;
  if (!profile) {
    return (
      <p className={hint} role="status">
        Loading your profile…
      </p>
    );
  }
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
    <div className="flex flex-col gap-12">
      <section className="flex flex-col gap-6">
        <header className="flex flex-col gap-2">
          <h1 className={pageTitle}>Hi, {profile.name}</h1>
          <p className="text-[17px] text-muted">What would you like to practice today?</p>
        </header>

        <form onSubmit={startLesson} className={`${panel} flex flex-col gap-3`}>
          <label htmlFor="topic" className={fieldLabel}>
            Lesson topic
          </label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              id="topic"
              className={`${input} sm:flex-1`}
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              placeholder={profile.main_topic}
              maxLength={200}
            />
            <button type="submit" className={`${buttonPrimary} shrink-0`} disabled={starting}>
              {starting ? "Starting…" : "Start lesson"}
            </button>
          </div>
          <p className={hint}>Leave it empty to practice your main topic: {profile.main_topic}.</p>
          {error ? <p className={errorText}>{error}</p> : null}
        </form>
      </section>

      {progress ? (
        <section className="flex flex-col gap-3">
          <h2 className={sectionTitle}>What your tutor has noticed</h2>
          <p className="max-w-[62ch] whitespace-pre-line border-l-2 border-fern pl-4 text-[17px] leading-relaxed">
            {progress.text}
          </p>
          <p className={`${hint} pl-[18px]`}>Updated after every lesson.</p>
        </section>
      ) : null}

      <section className="flex flex-col gap-3">
        <h2 className={sectionTitle}>Your lessons</h2>
        {lessons.length > 0 ? (
          <ul className="divide-y divide-line border-y border-line">
            {lessons.map((lesson) => (
              <li key={lesson.id}>
                <LessonRow lesson={lesson} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="max-w-[60ch] border-y border-line py-5 text-muted">
            No lessons yet. Start your first one above. When a lesson ends, the tutor writes a
            short summary and uses it to plan the next one.
          </p>
        )}
      </section>
    </div>
  );
}

const dateFormat = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
  year: "numeric",
});

function LessonRow({ lesson }: { lesson: Lesson }) {
  const completed = lesson.status === "summarized";
  return (
    <Link
      href={`/lesson/${lesson.id}`}
      className="-mx-2 flex items-center gap-4 rounded-xl px-2 py-4 transition-colors hover:bg-surface"
    >
      <span
        className={`flex size-8 shrink-0 items-center justify-center rounded-full ${
          completed ? "bg-fern-soft text-fern" : "border-2 border-ink"
        }`}
        aria-hidden
      >
        {completed ? <CheckIcon /> : <span className="size-2 rounded-full bg-ink" />}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-semibold">{lesson.topic}</span>
        <span className="text-sm text-muted">
          {completed ? "Completed" : "In progress"}, {dateFormat.format(new Date(lesson.created_at))}
        </span>
      </span>
      <ChevronRightIcon className="size-5 shrink-0 text-muted" />
    </Link>
  );
}
