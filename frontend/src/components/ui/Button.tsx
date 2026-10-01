import { clsx } from "clsx";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Link, type LinkProps } from "react-router";

import { Spinner } from "./Spinner";

/**
 * Buttons.
 * - primary:  near-black pill — the single most important action on a surface
 * - inverse:  white pill for dark bands
 * - outline:  1px pill for secondary actions and filters
 * - link:     underlined text action (the companion to a primary pill)
 * - ghost:    quiet icon / inline action
 * - danger:   outlined in error red — destructive actions
 */
export type ButtonVariant = "primary" | "inverse" | "outline" | "link" | "ghost" | "danger";
export type ButtonSize = "md" | "sm" | "icon";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-primary text-white hover:bg-primary-hover border border-primary",
  inverse: "bg-white text-primary hover:bg-stone border border-white",
  outline: "bg-transparent text-ink border border-primary hover:bg-primary hover:text-white",
  link: "bg-transparent text-ink underline underline-offset-4 decoration-hairline hover:decoration-ink border border-transparent",
  ghost: "bg-transparent text-ink hover:bg-stone border border-transparent",
  danger: "bg-transparent text-error border border-error hover:bg-error hover:text-white",
};

const SIZES: Record<ButtonSize, string> = {
  md: "min-h-11 px-6 text-sm",
  sm: "min-h-9 px-4 text-[0.8125rem]",
  icon: "h-10 w-10 justify-center",
};

export function buttonClass(variant: ButtonVariant = "primary", size: ButtonSize = "md", className?: string) {
  return clsx(
    "inline-flex select-none items-center gap-2 whitespace-nowrap font-medium leading-none no-underline transition-colors",
    variant === "link" ? "rounded-xs px-0" : "rounded-pill",
    "disabled:pointer-events-none disabled:opacity-40",
    VARIANTS[variant],
    // A text link keeps a 36px hit area and matches the type size of the pill beside it.
    variant === "link" ? clsx("min-h-9", size === "sm" ? "text-[0.8125rem]" : "text-sm") : SIZES[size],
    className,
  );
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    loading = false,
    className,
    children,
    disabled,
    type = "button",
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled ?? loading}
      aria-busy={loading || undefined}
      className={buttonClass(variant, size, className)}
      {...rest}
    >
      {loading ? <Spinner className="h-4 w-4" /> : null}
      {children}
    </button>
  );
});

/** A router link that looks like a button (for navigation, never for actions). */
export function ButtonLink({
  variant = "primary",
  size = "md",
  className,
  ...rest
}: LinkProps & { variant?: ButtonVariant; size?: ButtonSize }) {
  return <Link className={buttonClass(variant, size, className)} {...rest} />;
}
