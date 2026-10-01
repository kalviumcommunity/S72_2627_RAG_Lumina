import { clsx } from "clsx";

/** Mutually exclusive filter pills (research-filter style): outlined, selected fills near-black. */
export function Segmented<T extends string | number | boolean>({
  value,
  options,
  onChange,
  label,
  className,
}: {
  value: T;
  options: readonly (readonly [T, string])[];
  onChange: (value: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <div className={clsx("flex flex-wrap gap-2", className)} role="group" aria-label={label}>
      {options.map(([option, text]) => (
        <button
          key={String(option)}
          type="button"
          aria-pressed={value === option}
          onClick={() => onChange(option)}
          className={clsx(
            "inline-flex min-h-9 items-center whitespace-nowrap rounded-xl border px-4 text-sm transition-colors",
            value === option
              ? "border-primary bg-primary text-white"
              : "border-hairline bg-canvas text-ink hover:border-primary",
          )}
        >
          {text}
        </button>
      ))}
    </div>
  );
}
