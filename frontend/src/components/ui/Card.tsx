import { clsx } from "clsx";
import type { HTMLAttributes } from "react";

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={clsx("rounded-2xl border border-border bg-surface shadow-card", className)} {...rest} />
  );
}

export function CardHeader({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("flex items-start justify-between gap-3 px-5 pt-4", className)} {...rest} />;
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("px-5 py-4", className)} {...rest} />;
}
