import { clsx } from "clsx";
import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";

/** Rule-separated data table (research-table style): no boxes, tall rows, mono column labels. */
export function Table({
  children,
  label,
  className,
}: {
  children: ReactNode;
  label: string;
  className?: string;
}) {
  return (
    <div className={clsx("overflow-x-auto border-t border-primary", className)}>
      <table className="w-full text-left text-sm" aria-label={label}>
        {children}
      </table>
    </div>
  );
}

export function Th({ className, ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={clsx(
        "mono-label whitespace-nowrap border-b border-hairline px-3 py-3 font-normal text-muted first:pl-0",
        className,
      )}
      {...rest}
    />
  );
}

export function Td({ className, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={clsx("px-3 py-4 align-top first:pl-0", className)} {...rest} />;
}

export function Tr({ className, ...rest }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={clsx("border-b border-hairline", className)} {...rest} />;
}

/** A list of rule-separated rows (the default way to show records without boxing them). */
export function RuleList({ className, ...rest }: HTMLAttributes<HTMLUListElement>) {
  return <ul className={clsx("divide-y divide-hairline border-y border-hairline", className)} {...rest} />;
}
