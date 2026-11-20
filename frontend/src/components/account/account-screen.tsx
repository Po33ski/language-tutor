"use client";

import Link from "next/link";
import { useState } from "react";

import { useAccount } from "@/components/auth/auth-gate";
import { MIN_PASSWORD_LENGTH } from "@/components/auth/auth-screen";
import { AppHeader } from "@/components/brand";
import {
  buttonPrimary,
  buttonSecondary,
  errorText,
  fieldLabel,
  hint,
  input,
  pageTitle,
  sectionTitle,
} from "@/components/ui";
import { api, ApiError } from "@/lib/api/client";

export function AccountScreen() {
  const { account, signOut } = useAccount();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    await signOut();
  }

  return (
    <>
      <AppHeader />
      {/* Same width as the header, so the content lines up with the logo. */}
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-10 px-4 pb-16 pt-8 sm:px-6 sm:pt-12 [&>*]:max-w-xl">
        <header className="flex flex-col gap-2">
          <h1 className={pageTitle}>Your account</h1>
          <p className="text-[17px] text-muted">
            Signed in as <span className="break-all font-semibold text-ink">{account.email}</span>
          </p>
          <p className={hint}>
            Member since {new Date(account.created_at).toLocaleDateString()}
          </p>
        </header>

        {account.has_profile ? (
          <section className="flex flex-col items-start gap-3 border-t border-line pt-8">
            <h2 className={sectionTitle}>Learning profile</h2>
            <p className="text-muted">
              Your level, main topic, goal, lesson length and what the tutor should know.
            </p>
            <Link href="/profile" className={buttonSecondary}>
              Edit profile
            </Link>
          </section>
        ) : null}

        <ChangePasswordForm />

        <section className="flex flex-col items-start gap-3 border-t border-line pt-8">
          <h2 className={sectionTitle}>Sign out</h2>
          <p className="text-muted">
            Ends the session on this device. Changing your password signs out all other
            devices.
          </p>
          <button
            type="button"
            className={buttonSecondary}
            onClick={handleSignOut}
            disabled={signingOut}
          >
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
        </section>
      </main>
    </>
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
    <form onSubmit={submit} className="flex flex-col gap-5 border-t border-line pt-8">
      <h2 className={sectionTitle}>Change password</h2>
      <div className="flex flex-col gap-2">
        <label htmlFor="current-password" className={fieldLabel}>
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
        <label htmlFor="new-password" className={fieldLabel}>
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
        <p className={hint}>At least {MIN_PASSWORD_LENGTH} characters.</p>
      </div>
      {error ? (
        <p className={errorText} role="alert">
          {error}
        </p>
      ) : null}
      {done ? (
        <p className="text-sm font-semibold text-fern" role="status">
          Password changed. Other devices have been signed out.
        </p>
      ) : null}
      <button type="submit" className={`${buttonPrimary} w-full sm:w-auto sm:self-start`} disabled={busy}>
        {busy ? "Saving…" : "Change password"}
      </button>
    </form>
  );
}
