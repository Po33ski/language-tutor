"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api/client";

type Status = "checking" | "online" | "offline";

const LABELS: Record<Status, string> = {
  checking: "Checking backend…",
  online: "Backend online",
  offline: "Backend offline",
};

const DOT_COLORS: Record<Status, string> = {
  checking: "bg-zinc-400",
  online: "bg-emerald-500",
  offline: "bg-red-500",
};

export function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    const controller = new AbortController();
    api.getHealth(controller.signal)
      .then(() => setStatus("online"))
      .catch(() => {
        if (!controller.signal.aborted) setStatus("offline");
      });
    return () => controller.abort();
  }, []);

  return (
    <p className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
      <span className={`h-2 w-2 rounded-full ${DOT_COLORS[status]}`} aria-hidden />
      {LABELS[status]}
    </p>
  );
}
