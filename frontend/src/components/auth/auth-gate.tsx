"use client";

import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import { AuthScreen } from "@/components/auth/auth-screen";
import { Wordmark } from "@/components/brand";
import { buttonPrimary } from "@/components/ui";
import { api, ApiError, type Account } from "@/lib/api/client";
import { forgetLegacyStorage, setSessionToken, useSessionToken } from "@/lib/session";

interface AccountContextValue {
  account: Account;
  /** Re-read the account (e.g. after onboarding created the profile). */
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AccountContext = createContext<AccountContextValue | null>(null);

/** The signed-in account. Only usable below `AuthGate`, which renders nothing else. */
export function useAccount(): AccountContextValue {
  const value = use(AccountContext);
  if (!value) throw new Error("useAccount must be used inside AuthGate");
  return value;
}

type Check =
  | { token: string; status: "signed-in"; account: Account }
  | { token: string; status: "offline" };

const subscribeNever = () => () => {};

/**
 * Shows the app to signed-in users and the sign-in / sign-up screen to everyone else.
 * A stored session is checked against the backend once per page load; any later 401
 * clears it (in the API client), which brings the sign-in screen back.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  // localStorage is unknown during server rendering and hydration: wait for the client,
  // so signed-in users do not see the sign-in screen flash.
  const hydrated = useSyncExternalStore(subscribeNever, () => true, () => false);
  const token = useSessionToken();
  const [check, setCheck] = useState<Check | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => forgetLegacyStorage(), []);

  useEffect(() => {
    if (token === null) return;
    const controller = new AbortController();
    api
      .getAccount(controller.signal)
      .then((account) => setCheck({ token, status: "signed-in", account }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        // A 401 has already cleared the token; anything else means the server is down.
        if (!(error instanceof ApiError && error.status === 401)) {
          setCheck({ token, status: "offline" });
        }
      });
    return () => controller.abort();
  }, [token, attempt]);

  const refresh = useCallback(async () => {
    if (token === null) return;
    const account = await api.getAccount();
    setCheck({ token, status: "signed-in", account });
  }, [token]);

  const signOut = useCallback(async () => {
    await api.signOut().catch(() => {});
    setSessionToken(null);
  }, []);

  const current = check !== null && check.token === token ? check : null;
  const value = useMemo(
    () =>
      current?.status === "signed-in" ? { account: current.account, refresh, signOut } : null,
    [current, refresh, signOut],
  );

  if (!hydrated) return <Pending />;
  if (token === null) return <AuthScreen />;
  if (current === null) return <Pending />;
  if (current.status === "offline") {
    return (
      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-5 px-4">
        <Wordmark />
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-bold tracking-[-0.01em]">Can&apos;t reach the server</h1>
          <p className="text-muted">Check your internet connection, then try again.</p>
        </div>
        <button
          type="button"
          className={`${buttonPrimary} self-start`}
          onClick={() => setAttempt((n) => n + 1)}
        >
          Try again
        </button>
      </main>
    );
  }
  return <AccountContext value={value}>{children}</AccountContext>;
}

function Pending() {
  return (
    <p className="m-auto text-sm text-muted" role="status">
      Loading…
    </p>
  );
}
