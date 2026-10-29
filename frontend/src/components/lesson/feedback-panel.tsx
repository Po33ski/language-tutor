import { card } from "@/components/ui";
import type { Mistake, VocabularyItem } from "@/lib/api/client";

interface FeedbackPanelProps {
  mistakes: Mistake[];
  vocabulary: VocabularyItem[];
}

export function FeedbackPanel({ mistakes, vocabulary }: FeedbackPanelProps) {
  return (
    <div className="flex flex-col gap-6">
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Corrections ({mistakes.length})
        </h2>
        {mistakes.length === 0 ? (
          <p className="text-sm text-zinc-500">No corrections yet. Keep talking!</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {/* Newest first, so the latest correction is always visible. */}
            {mistakes.toReversed().map((mistake, index) => (
              <li key={mistakes.length - index} className={`${card} flex flex-col gap-1 text-sm`}>
                <span className="text-red-600 line-through decoration-red-400 dark:text-red-400">
                  {mistake.original}
                </span>
                <span className="font-medium text-emerald-700 dark:text-emerald-400">
                  {mistake.corrected}
                </span>
                <span className="text-zinc-600 dark:text-zinc-400">{mistake.explanation}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">
          Vocabulary ({vocabulary.length})
        </h2>
        {vocabulary.length === 0 ? (
          <p className="text-sm text-zinc-500">New words from the lesson will appear here.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {vocabulary.toReversed().map((item, index) => (
              <li key={vocabulary.length - index} className={`${card} flex flex-col gap-1 text-sm`}>
                <span className="font-medium">{item.word}</span>
                <span className="text-zinc-600 dark:text-zinc-400">{item.meaning}</span>
                <span className="italic text-zinc-500">“{item.example}”</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
