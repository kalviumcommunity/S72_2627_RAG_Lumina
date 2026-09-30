import * as DialogPrimitive from "@radix-ui/react-dialog";
import { clsx } from "clsx";
import { X } from "lucide-react";
import type { ReactNode } from "react";

/** Bottom sheet on phones, right-hand side panel on wider screens. */
export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/40 data-[state=open]:animate-[fade-in_150ms_ease-out]" />
        <DialogPrimitive.Content
          className={clsx(
            "fixed z-50 flex flex-col bg-surface text-text shadow-2xl outline-none",
            "inset-x-0 bottom-0 max-h-[92dvh] rounded-t-3xl border-t border-border",
            "md:inset-y-0 md:right-0 md:left-auto md:max-h-none md:w-[min(760px,92vw)] md:rounded-none md:rounded-l-2xl md:border-l md:border-t-0",
          )}
        >
          <div className="mx-auto mt-2 h-1.5 w-12 rounded-full bg-border-strong md:hidden" aria-hidden />
          <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-3">
            <div className="min-w-0">
              <DialogPrimitive.Title className="text-lg font-semibold leading-snug">
                {title}
              </DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="mt-0.5 text-sm text-muted">
                  {description}
                </DialogPrimitive.Description>
              ) : (
                <DialogPrimitive.Description className="sr-only">Source document</DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl hover:bg-surface-2"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </DialogPrimitive.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4">{children}</div>
          {footer ? <div className="border-t border-border px-5 py-3">{footer}</div> : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
