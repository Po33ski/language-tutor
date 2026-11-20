import Link from "next/link";
import type { ReactNode } from "react";

/** The app's mark: a speech bubble with a check, i.e. conversation plus correction. */
export function Wordmark() {
  return (
    <span className="inline-flex items-center gap-2 text-[17px] font-bold tracking-[-0.01em]">
      <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
        <path
          d="M5.5 3h13A2.5 2.5 0 0 1 21 5.5v9a2.5 2.5 0 0 1-2.5 2.5H11l-5 4.5V17h-.5A2.5 2.5 0 0 1 3 14.5v-9A2.5 2.5 0 0 1 5.5 3Z"
          fill="var(--fern)"
        />
        <path
          d="m8 10.2 2.6 2.6L16 7.6"
          fill="none"
          stroke="var(--paper)"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      Language Tutor
    </span>
  );
}

/** Top bar of the regular pages: the mark (links home) and an optional action. */
export function AppHeader({ action }: { action?: ReactNode }) {
  return (
    <header className="border-b border-line">
      <div className="mx-auto flex h-16 w-full max-w-3xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link href="/" className="rounded-lg" aria-label="Language Tutor, home">
          <Wordmark />
        </Link>
        {action}
      </div>
    </header>
  );
}
