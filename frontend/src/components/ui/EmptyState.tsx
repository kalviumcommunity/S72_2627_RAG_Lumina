import type { ReactNode } from "react";

/** Soft stone placeholder for "nothing here yet". */
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
    <div className="flex flex-col items-start gap-2 rounded-lg bg-stone px-6 py-10 sm:px-10">
      {icon ? <div className="text-muted">{icon}</div> : null}
      <p className="text-feature">{title}</p>
      {children ? <div className="max-w-xl text-caption text-muted">{children}</div> : null}
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
    <div role="alert" className="rounded-sm border border-error bg-error-wash px-4 py-3 text-sm">
      <p className="font-medium text-error">{title}</p>
      <p className="mt-0.5 text-ink">{message}</p>
    </div>
  );
}
