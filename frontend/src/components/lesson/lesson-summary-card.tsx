import { CheckIcon } from "@/components/icons";
import type { LessonSummary } from "@/lib/api/client";

/** The tutor's wrap-up, shown at the end of the conversation. */
export function LessonSummaryCard({ summary }: { summary: LessonSummary }) {
  return (
    <section className="flex flex-col gap-5 rounded-3xl bg-fern-soft p-5 sm:p-6">
      <div className="flex flex-col gap-2">
        <h2 className="flex items-center gap-2 text-[17px] font-bold text-fern">
          <span className="flex size-6 items-center justify-center rounded-full bg-fern text-paper">
            <CheckIcon className="size-3.5" />
          </span>
          Lesson complete
        </h2>
        <p className="text-[17px] leading-relaxed">{summary.summary}</p>
      </div>
      <div className="grid gap-5 sm:grid-cols-2">
        <SummaryList title="What you practiced" items={summary.practiced} />
        <SummaryList title="Mistakes to watch" items={summary.recurring_mistakes} />
        <SummaryList title="New vocabulary" items={summary.vocabulary} />
        <SummaryList title="Next time" items={summary.next_steps} />
      </div>
    </section>
  );
}

function SummaryList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <h3 className="text-[15px] font-bold">{title}</h3>
      <ul className="list-disc space-y-1 pl-5 text-[15px] leading-relaxed marker:text-fern">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
