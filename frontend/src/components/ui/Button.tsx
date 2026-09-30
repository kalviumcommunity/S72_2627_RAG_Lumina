import { clsx } from "clsx";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "subtle";
type Size = "md" | "sm" | "icon";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-fg hover:bg-accent-hover border border-transparent",
  secondary: "bg-surface text-text border border-border-strong hover:bg-surface-2",
  ghost: "bg-transparent text-text border border-transparent hover:bg-surface-2",
  subtle: "bg-accent-soft text-accent-text border border-transparent hover:brightness-95",
  danger: "bg-danger text-white border border-transparent hover:brightness-110",
};

// 44 px minimum touch target (md / icon); sm is for dense desktop tables only.
const SIZES: Record<Size, string> = {
  md: "min-h-11 px-4 text-[0.95rem]",
  sm: "min-h-10 px-3 text-sm",
  icon: "h-11 w-11 justify-center",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
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
      className={clsx(
        "inline-flex select-none items-center gap-2 rounded-xl font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner className="h-4 w-4" /> : null}
      {children}
    </button>
  );
});
