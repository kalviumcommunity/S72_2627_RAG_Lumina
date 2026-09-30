import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  wide = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <DialogPrimitive.Content
          className={`fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border bg-surface p-5 shadow-2xl outline-none ${
            wide ? "max-w-3xl" : "max-w-lg"
          }`}
        >
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <DialogPrimitive.Title className="text-lg font-semibold">{title}</DialogPrimitive.Title>
              <DialogPrimitive.Description className={description ? "mt-1 text-sm text-muted" : "sr-only"}>
                {description ?? title}
              </DialogPrimitive.Description>
            </div>
            <DialogPrimitive.Close
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl hover:bg-surface-2"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </DialogPrimitive.Close>
          </div>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
