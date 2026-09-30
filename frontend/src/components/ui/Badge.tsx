import { clsx } from "clsx";
import type { HTMLAttributes } from "react";

export type Tone = "neutral" | "accent" | "amber" | "danger" | "success";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted border-border",
  accent: "bg-accent-soft text-accent-text border-transparent",
  amber: "bg-amber-soft text-amber border-amber-border",
  danger: "bg-danger-soft text-danger border-danger-border",
  success: "bg-success-soft text-success border-transparent",
};

export function Badge({
  tone = "neutral",
  className,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
      {...rest}
    />
  );
}
