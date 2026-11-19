"use client";

import Link from "next/link";
import { useState } from "react";

import { useAccount } from "@/components/auth/auth-gate";
import { MIN_PASSWORD_LENGTH } from "@/components/auth/auth-screen";
import { buttonPrimary, buttonSecondary, card, errorText, input } from "@/components/ui";
import { api, ApiError } from "@/lib/api/client";

export function AccountScreen() {
  const { account, signOut } = useAccount();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    await signOut();
  }

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 px-4 py-12">
      <header className="flex flex-col gap-2">
        <Link href="/" className="text-sm text-zinc-500 hover:underline">
          ← Back
        </Link>
        <h1 className="text-2xl font-semibold tracking-tight">Your account</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Signed in as <span className="font-medium">{account.email}</span> · member since{" "}
          {new Date(account.created_at).toLocaleDateString()}
        </p>
      </header>

      <ChangePasswordForm />

      <section className={`${card} flex flex-col gap-3`}>
        <h2 className="font-medium">Sign out</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Ends the session on this device. Changing your password signs out all other devices.
        </p>
        <button
          type="button"
          className={`${buttonSecondary} self-start`}
          onClick={handleSignOut}
          disabled={signingOut}
        >
          {signingOut ? "Signing out…" : "Sign out"}
        </button>
      </section>
    </main>
  );
}

function ChangePasswordForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      await api.changePassword(
        String(form.get("current-password") ?? ""),
        String(form.get("new-password") ?? ""),
      );
      formElement.reset();
      setDone(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not change the password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className={`${card} flex flex-col gap-4`}>
      <h2 className="font-medium">Change password</h2>
      <div className="flex flex-col gap-2">
        <label htmlFor="current-password" className="text-sm font-medium">
          Current password
        </label>
        <input
          id="current-password"
          name="current-password"
          type="password"
          autoComplete="current-password"
          required
          maxLength={128}
          className={input}
        />
      </div>
      <div className="flex flex-col gap-2">
        <label htmlFor="new-password" className="text-sm font-medium">
          New password
        </label>
        <input
          id="new-password"
          name="new-password"
          type="password"
          autoComplete="new-password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          maxLength={128}
          className={input}
        />
        <p className="text-xs text-zinc-500">At least {MIN_PASSWORD_LENGTH} characters.</p>
      </div>
      {error ? (
        <p className={errorText} role="alert">
          {error}
        </p>
      ) : null}
      {done ? (
        <p className="text-sm text-emerald-700 dark:text-emerald-400" role="status">
          Password changed. Other devices have been signed out.
        </p>
      ) : null}
      <button type="submit" className={`${buttonPrimary} self-start`} disabled={busy}>
        {busy ? "Saving…" : "Change password"}
      </button>
    </form>
  );
}
