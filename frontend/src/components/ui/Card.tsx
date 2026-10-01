import { clsx } from "clsx";
import type { HTMLAttributes } from "react";

/**
 * Surfaces. Flat — containment comes from a hairline or a change of surface, never a shadow.
 * - default: white card with a hairline, 16px radius
 * - stone:   warm neutral block (product-card style), 8px radius
 * - dark:    near-black product panel, 22px radius
 * - soft:    the palest border, for grouping on white
 */
type CardTone = "default" | "stone" | "dark" | "soft";

const TONES: Record<CardTone, string> = {
  default: "rounded-md border border-hairline bg-canvas",
  stone: "rounded-sm bg-stone",
  dark: "rounded-lg bg-primary text-white",
  soft: "rounded-md border border-card-border bg-canvas",
};

export function Card({
  tone = "default",
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { tone?: CardTone }) {
  return <div className={clsx(TONES[tone], className)} {...rest} />;
}

/** Full-width section band: deep green or navy for product moments, stone for warm blocks. */
export function Band({
  tone = "green",
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLElement> & { tone?: "green" | "navy" | "stone" | "dark" }) {
  const tones = {
    green: "bg-green text-white",
    navy: "bg-navy text-white",
    stone: "bg-stone text-ink",
    dark: "bg-primary text-white",
  } as const;
  return (
    <section className={clsx(tones[tone], className)} {...rest}>
      {children}
    </section>
  );
}
