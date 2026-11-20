"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Wordmark } from "@/components/brand";
import { CheckIcon } from "@/components/icons";
import { buttonPrimary, errorText, fieldLabel, hint, input, pageTitle } from "@/components/ui";
import { api, ApiError } from "@/lib/api/client";
import { setSessionToken } from "@/lib/session";

type Mode = "sign-in" | "sign-up";

// Mirrors the backend policy (NIST SP 800-63B-4), which has the final word.
export const MIN_PASSWORD_LENGTH = 15;

/** Sign in, or create an account. Rendered by `AuthGate` instead of the app. */
export function AuthScreen() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("sign-in");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const signingUp = mode === "sign-up";

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    setBusy(true);
    setError(null);
    try {
      const { token } = signingUp
        ? await api.signUp(email, password)
        : await api.signIn(email, password);
      // A new account has no learner profile yet: go straight to the onboarding form.
      if (signingUp) router.push("/onboarding");
      setSessionToken(token);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
  }

  return (
    <main className="flex flex-1 flex-col lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section className="flex flex-col px-4 py-6 sm:px-8 lg:px-12">
        <Wordmark />
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-8 py-10">
          <header className="flex flex-col gap-3">
            <h1 className={pageTitle}>{signingUp ? "Create your account" : "Welcome back"}</h1>
            <p className="text-[17px] leading-relaxed text-muted">
              Practice English by talking with an AI tutor. It corrects you as you go and
              remembers what to work on next time.
            </p>
          </header>

          <div className="grid grid-cols-2 rounded-full bg-surface p-1 text-[15px]">
            {(["sign-in", "sign-up"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => switchMode(option)}
                aria-pressed={mode === option}
                className={`min-h-10 rounded-full px-3 font-semibold transition-colors ${
                  mode === option
                    ? "bg-paper text-ink shadow-[0_1px_2px_rgb(0_0_0/0.08)]"
                    : "text-muted hover:text-ink"
                }`}
              >
                {option === "sign-in" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>

          {/* key: a fresh form per mode, so the browser offers the right saved password. */}
          <form key={mode} onSubmit={submit} className="flex flex-col gap-5">
            <div className="flex flex-col gap-2">
              <label htmlFor="email" className={fieldLabel}>
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete={signingUp ? "email" : "username"}
                required
                maxLength={254}
                className={input}
              />
            </div>
            <div className="flex flex-col gap-2">
              <label htmlFor="password" className={fieldLabel}>
                Password
              </label>
              <input
                id="password"
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete={signingUp ? "new-password" : "current-password"}
                required
                minLength={signingUp ? MIN_PASSWORD_LENGTH : undefined}
                maxLength={128}
                className={input}
              />
              {signingUp ? (
                <p className={hint}>
                  At least {MIN_PASSWORD_LENGTH} characters. A few random words, like
                  &ldquo;purple elephants dance at noon&rdquo;, are strong and easy to
                  remember.
                </p>
              ) : null}
              <label className="flex w-fit items-center gap-2 py-1 text-sm text-muted">
                <input
                  type="checkbox"
                  className="size-4 accent-fern"
                  checked={showPassword}
                  onChange={(event) => setShowPassword(event.target.checked)}
                />
                Show password
              </label>
            </div>
            {error ? (
              <p className={errorText} role="alert">
                {error}
              </p>
            ) : null}
            <button type="submit" className={`${buttonPrimary} w-full`} disabled={busy}>
              {busy ? "Please wait…" : signingUp ? "Create account" : "Sign in"}
            </button>
          </form>
        </div>
      </section>

      <SampleLesson />
    </main>
  );
}

/** A short example exchange: what a lesson looks like, including a correction. */
function SampleLesson() {
  return (
    <figure className="flex flex-col justify-center gap-6 bg-surface px-4 py-10 sm:px-8 lg:px-16">
      <div className="mx-auto flex w-full max-w-md flex-col gap-3 text-[15px] leading-relaxed">
        <p className="max-w-[85%] self-start rounded-[20px] rounded-bl-md bg-paper px-4 py-3">
          How long have you worked as a developer?
        </p>
        <p className="max-w-[85%] self-end rounded-[20px] rounded-br-md bg-ink px-4 py-3 text-paper">
          I work as a developer since five years.
        </p>
        <div className="flex flex-col gap-1 rounded-2xl border border-line bg-paper px-4 py-3">
          <span className="text-muted line-through decoration-muted/70">
            I work … since five years
          </span>
          <span className="flex items-center gap-1.5 font-semibold text-fern">
            <CheckIcon />
            I&apos;ve worked … for five years
          </span>
          <span className="text-sm text-muted">
            For a length of time up to now, use the present perfect with &ldquo;for&rdquo;.
          </span>
        </div>
        <p className="max-w-[85%] self-start rounded-[20px] rounded-bl-md bg-paper px-4 py-3">
          Nice! Small fix: we say &ldquo;I&apos;ve worked as a developer for five
          years.&rdquo; What do you enjoy most about it?
        </p>
      </div>
      <figcaption className="mx-auto w-full max-w-md text-sm text-muted">
        What a lesson looks like: you answer by voice or text, and the tutor corrects you
        while it keeps the conversation going.
      </figcaption>
    </figure>
  );
}
