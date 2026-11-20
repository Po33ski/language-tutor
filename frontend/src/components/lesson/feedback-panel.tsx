import { CheckIcon } from "@/components/icons";
import type { Mistake, VocabularyItem } from "@/lib/api/client";

interface FeedbackPanelProps {
  mistakes: Mistake[];
  vocabulary: VocabularyItem[];
}

export function FeedbackPanel({ mistakes, vocabulary }: FeedbackPanelProps) {
  return (
    <div className="flex flex-col gap-8 px-5 py-6">
      <section className="flex flex-col gap-2">
        <h2 className="flex items-baseline gap-2 text-[17px] font-bold">
          Corrections <span className="text-sm font-normal text-muted">{mistakes.length}</span>
        </h2>
        {mistakes.length === 0 ? (
          <p className="text-sm text-muted">Corrections appear here as you talk.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line">
            {/* Newest first, so the latest correction is always visible. */}
            {mistakes.toReversed().map((mistake, index) => (
              <li key={mistakes.length - index} className="flex flex-col gap-1 py-3">
                <span className="text-[15px] text-muted line-through decoration-muted/70">
                  {mistake.original}
                </span>
                <span className="flex items-start gap-1.5 text-[15px] font-semibold text-fern">
                  <CheckIcon className="mt-[3px] size-4 shrink-0" />
                  {mistake.corrected}
                </span>
                <span className="text-sm leading-relaxed text-muted">{mistake.explanation}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="flex items-baseline gap-2 text-[17px] font-bold">
          Vocabulary <span className="text-sm font-normal text-muted">{vocabulary.length}</span>
        </h2>
        {vocabulary.length === 0 ? (
          <p className="text-sm text-muted">New words from the lesson appear here.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line">
            {vocabulary.toReversed().map((item, index) => (
              <li key={vocabulary.length - index} className="flex flex-col gap-1 py-3">
                <span className="text-[15px] font-bold">{item.word}</span>
                <span className="text-sm leading-relaxed">{item.meaning}</span>
                <span className="text-sm italic leading-relaxed text-muted">
                  &ldquo;{item.example}&rdquo;
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
