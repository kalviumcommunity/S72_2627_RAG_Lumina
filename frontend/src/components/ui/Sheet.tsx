import * as DialogPrimitive from "@radix-ui/react-dialog";
import { clsx } from "clsx";
import { X } from "lucide-react";
import type { ReactNode } from "react";

/** Bottom sheet on phones, right-hand side panel on wider screens. */
export function Sheet({
  open,
  onOpenChange,
  title,
  eyebrow,
  description,
  children,
  footer,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  eyebrow?: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-primary/50" />
        <DialogPrimitive.Content
          className={clsx(
            "fixed z-50 flex flex-col bg-canvas text-ink outline-none",
            "inset-x-0 bottom-0 max-h-[92dvh] rounded-t-lg",
            "md:inset-y-0 md:left-auto md:right-0 md:max-h-none md:w-[min(760px,92vw)] md:rounded-none",
          )}
        >
          <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-hairline md:hidden" aria-hidden />
          <div className="flex items-start justify-between gap-4 border-b border-hairline px-6 py-5">
            <div className="min-w-0">
              {eyebrow ? <div className="mono-label mb-1.5 text-muted">{eyebrow}</div> : null}
              <DialogPrimitive.Title className="text-card-heading">{title}</DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="mt-1 text-caption text-muted">
                  {description}
                </DialogPrimitive.Description>
              ) : (
                <DialogPrimitive.Description className="sr-only">Source document</DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close
              className="-mr-2 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full hover:bg-stone"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </DialogPrimitive.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-5">{children}</div>
          {footer ? <div className="border-t border-hairline px-6 py-4">{footer}</div> : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
