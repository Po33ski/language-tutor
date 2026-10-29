import { card } from "@/components/ui";
import type { LessonSummary } from "@/lib/api/client";

export function LessonSummaryCard({ summary }: { summary: LessonSummary }) {
  return (
    <section className={`${card} flex flex-col gap-4 border-emerald-300 dark:border-emerald-800`}>
      <div className="flex flex-col gap-1">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-400">
          Lesson summary
        </h2>
        <p className="text-sm leading-relaxed">{summary.summary}</p>
      </div>
      <SummaryList title="What you practiced" items={summary.practiced} />
      <SummaryList title="Mistakes to watch" items={summary.recurring_mistakes} />
      <SummaryList title="New vocabulary" items={summary.vocabulary} />
      <SummaryList title="Next time" items={summary.next_steps} />
    </section>
  );
}

function SummaryList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{title}</h3>
      <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-700 dark:text-zinc-300">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
