"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { buttonPrimary, card, errorText, input } from "@/components/ui";
import { setAccessKey, useAccessKey } from "@/lib/access-key";
import { checkAccess } from "@/lib/api/client";

type Access = "granted" | "denied" | "unreachable";

interface CheckResult {
  key: string | null;
  access: Access;
}

/**
 * Shows the app once the backend accepts the stored access key (or needs none);
 * otherwise asks for the key. Any later 401 clears the key, which brings this back.
 */
export function AccessGate({ children }: { children: ReactNode }) {
  const key = useAccessKey();
  const [result, setResult] = useState<CheckResult | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    checkAccess(key, controller.signal)
      .then((access) => setResult({ key, access }))
      .catch(() => {
        if (!controller.signal.aborted) setResult({ key, access: "unreachable" });
      });
    return () => controller.abort();
  }, [key]);

  // A result for a different key is stale: the key changed and a new check is running.
  const access = result?.key === key ? result.access : null;

  if (access === null) {
    return <p className="m-auto text-sm text-zinc-500">Connecting…</p>;
  }
  if (access === "denied") {
    return <AccessKeyForm rejected={key !== null} />;
  }
  // "unreachable": show the app anyway; its own error states say the backend is offline.
  return children;
}

function AccessKeyForm({ rejected }: { rejected: boolean }) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("access-key");
    if (typeof value === "string" && value.trim()) setAccessKey(value.trim());
  }

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 px-4 py-12">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Language Tutor</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Enter the access key to continue. You only need to do this once on this device.
        </p>
      </header>
      <form onSubmit={submit} className={`${card} flex flex-col gap-4`}>
        <label htmlFor="access-key" className="text-sm font-medium">
          Access key
        </label>
        <input
          id="access-key"
          name="access-key"
          type="password"
          autoComplete="current-password"
          required
          className={input}
        />
        {rejected ? <p className={errorText}>That access key is not valid.</p> : null}
        <button type="submit" className={`${buttonPrimary} self-start`}>
          Continue
        </button>
      </form>
    </main>
  );
}
