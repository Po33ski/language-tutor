"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { buttonPrimary, card, errorText, input } from "@/components/ui";
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
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 px-4 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Language Tutor</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Practice English through conversation with an AI tutor.
        </p>
      </header>

      <div className="grid grid-cols-2 rounded-lg border border-zinc-300 p-1 text-sm dark:border-zinc-700">
        {(["sign-in", "sign-up"] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => switchMode(option)}
            aria-pressed={mode === option}
            className={`rounded-md px-3 py-1.5 font-medium transition-colors ${
              mode === option
                ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
            }`}
          >
            {option === "sign-in" ? "Sign in" : "Create account"}
          </button>
        ))}
      </div>

      {/* key: a fresh form per mode, so the browser offers the right saved password. */}
      <form key={mode} onSubmit={submit} className={`${card} flex flex-col gap-4`}>
        <div className="flex flex-col gap-2">
          <label htmlFor="email" className="text-sm font-medium">
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
          <label htmlFor="password" className="text-sm font-medium">
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
            <p className="text-xs text-zinc-500">
              At least {MIN_PASSWORD_LENGTH} characters. Tip: a few random words, like
              &ldquo;purple elephants dance at noon&rdquo;, are strong and easy to remember.
            </p>
          ) : null}
          <label className="flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400">
            <input
              type="checkbox"
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
        <button type="submit" className={`${buttonPrimary} self-start`} disabled={busy}>
          {busy ? "Please wait…" : signingUp ? "Create account" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
