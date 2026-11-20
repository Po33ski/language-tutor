import { Suspense } from "react";

import { LessonView } from "@/components/lesson/lesson-view";

export default function LessonPage(props: PageProps<"/lesson/[id]">) {
  // `params` is read inside the Suspense boundary, so the rest of the page can be
  // prerendered as a static shell (Cache Components).
  return (
    <Suspense fallback={<p className="m-auto text-sm text-muted">Loading lesson…</p>}>
      <LessonView params={props.params} />
    </Suspense>
  );
}
