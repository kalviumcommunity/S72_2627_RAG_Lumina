import type { ReactNode } from "react";

export function EmptyState({
  icon,
  title,
  children,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-border px-6 py-10 text-center">
      {icon ? <div className="text-muted">{icon}</div> : null}
      <p className="font-medium">{title}</p>
      {children ? <div className="max-w-md text-sm text-muted">{children}</div> : null}
    </div>
  );
}

export function ErrorNotice({
  title = "Something went wrong",
  message,
}: {
  title?: string;
  message: string;
}) {
  return (
    <div role="alert" className="rounded-2xl border border-danger-border bg-danger-soft px-4 py-3 text-sm">
      <p className="font-medium text-danger">{title}</p>
      <p className="mt-0.5 text-text">{message}</p>
    </div>
  );
}
