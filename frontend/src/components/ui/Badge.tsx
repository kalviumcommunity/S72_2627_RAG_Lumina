import { clsx } from "clsx";
import type { HTMLAttributes } from "react";

/**
 * Status chips. Colour is reserved for meaning:
 * - success  pale green wash, deep green text   (approved, verified, in force)
 * - amber    coral outline                       (needs attention: draft links, superseded, partly)
 * - danger   error-red outline                   (retired, overdue, refused)
 * - accent   ink outline                         (neutral emphasis)
 * - neutral  stone fill                          (metadata)
 */
export type Tone = "neutral" | "accent" | "amber" | "danger" | "success";

const TONES: Record<Tone, string> = {
  neutral: "bg-stone text-ink border-stone",
  accent: "bg-canvas text-ink border-ink",
  amber: "bg-coral-wash text-coral-ink border-coral-soft",
  danger: "bg-error-wash text-error border-error",
  success: "bg-green-wash text-green border-green/25",
};

export function Badge({
  tone = "neutral",
  className,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-xs border px-2 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
      {...rest}
    />
  );
}

/** Uppercase monospace system marker ("VERSION 3", "S1", "CIRCULAR"). */
export function MonoLabel({ className, ...rest }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={clsx("mono-label text-muted", className)} {...rest} />;
}

/** Coral taxonomy chip (document types, example categories). `active` inverts to a coral fill. */
export function TaxonomyChip({
  active = false,
  className,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { active?: boolean }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center whitespace-nowrap rounded-sm border px-2.5 py-0.5 text-xs",
        active ? "border-coral bg-coral text-primary" : "border-coral-soft bg-coral-wash text-coral-ink",
        className,
      )}
      {...rest}
    />
  );
}
