// Shared Tailwind class names, so pages look consistent without a component library.
// Colors come from the tokens in `app/globals.css` (paper, ink, surface, line, muted,
// fern, danger). Radius follows the role: pills for actions, rounded-xl for fields,
// rounded-3xl for large surfaces.

export const buttonPrimary =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-ink px-5 text-[15px] font-semibold text-paper transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40";

export const buttonSecondary =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-line px-5 text-[15px] font-semibold text-ink transition-colors hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40";

/** Round, icon-only button (give it an `aria-label`). */
export const iconButton =
  "inline-flex size-11 shrink-0 items-center justify-center rounded-full text-ink transition-colors hover:bg-surface disabled:cursor-not-allowed disabled:opacity-40";

export const input =
  "w-full rounded-xl border border-line bg-paper px-3.5 py-2.5 text-base text-ink outline-none transition-colors placeholder:text-muted/80 focus:border-fern focus:ring-3 focus:ring-fern/15 disabled:opacity-60";

export const fieldLabel = "text-[15px] font-semibold";

export const hint = "text-sm text-muted";

/** A quiet grey panel; content sits on it without borders or shadows. */
export const panel = "rounded-3xl bg-surface p-5 sm:p-6";

export const pageTitle = "text-3xl font-bold leading-tight tracking-[-0.02em] sm:text-4xl";

export const sectionTitle = "text-xl font-bold tracking-[-0.01em]";

export const errorText = "text-sm text-danger";

export const textLink = "font-semibold text-ink underline decoration-line underline-offset-4 hover:decoration-ink";
