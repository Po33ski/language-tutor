"use client";

import { useEffect, useState } from "react";

/** The final stretch in which the tutor wraps up. Same rule as the backend
 * (`app/agent/clock.py`): 20% of the lesson, between 1 and 3 minutes. */
export function wrapUpSeconds(durationMinutes: number): number {
  return 60 * Math.min(3, Math.max(1, Math.round(durationMinutes * 0.2)));
}

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

interface LessonTimerProps {
  /** When the lesson's time runs out, in this device's clock (ms). */
  deadline: number;
  durationMinutes: number;
  /** Called once, when the countdown reaches zero. */
  onTimeUp: () => void;
}

/**
 * The countdown under the lesson title, with a progress bar along the bottom edge of the
 * header (the nearest positioned ancestor). It re-renders itself every second, so the
 * rest of the lesson does not.
 */
export function LessonTimer({ deadline, durationMinutes, onTimeUp }: LessonTimerProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= deadline) {
        window.clearInterval(id);
        onTimeUp();
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [deadline, onTimeUp]);

  const total = durationMinutes * 60;
  const left = Math.max(0, Math.ceil((deadline - now) / 1000));
  const wrappingUp = left > 0 && left <= wrapUpSeconds(durationMinutes);
  const used = Math.min(1, Math.max(0, (total - left) / total));

  return (
    <>
      <span role="timer" aria-label={left > 0 ? `${formatTime(left)} left` : "Time's up"}>
        {left === 0 ? (
          <span className="font-semibold text-ink">Time&apos;s up</span>
        ) : wrappingUp ? (
          <>
            <span className="font-semibold tabular-nums text-ink">{formatTime(left)}</span> left,
            time to wrap up
          </>
        ) : (
          <>
            <span className="tabular-nums">{formatTime(left)}</span> left
          </>
        )}
      </span>
      <span
        className="absolute inset-x-0 bottom-0 h-0.5 origin-left bg-fern transition-transform duration-1000 ease-linear motion-reduce:transition-none"
        style={{ transform: `scaleX(${used})` }}
        aria-hidden
      />
    </>
  );
}
