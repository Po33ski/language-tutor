"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api/client";

/** A warning that appears only when the server cannot be reached. */
export function BackendStatus() {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    api.getHealth(controller.signal).catch(() => {
      if (!controller.signal.aborted) setOffline(true);
    });
    return () => controller.abort();
  }, []);

  if (!offline) return null;
  return (
    <p className="flex items-center gap-2 rounded-xl border border-line px-4 py-3 text-sm" role="status">
      <span className="size-2 shrink-0 rounded-full bg-danger" aria-hidden />
      Can&apos;t reach the server right now. Lessons won&apos;t start until it&apos;s back.
    </p>
  );
}
