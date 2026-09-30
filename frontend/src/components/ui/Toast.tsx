import * as ToastPrimitive from "@radix-ui/react-toast";
import { clsx } from "clsx";
import { CheckCircle2, AlertTriangle, X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type ToastTone = "success" | "error" | "info";
interface ToastItem {
  id: number;
  title: string;
  description?: string;
  tone: ToastTone;
}

interface ToastApi {
  notify: (title: string, options?: { description?: string; tone?: ToastTone }) => void;
}

const ToastContext = createContext<ToastApi>({ notify: () => undefined });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const notify = useCallback<ToastApi["notify"]>((title, options) => {
    setItems((prev) => [
      ...prev,
      {
        id: Date.now() + Math.random(),
        title,
        description: options?.description,
        tone: options?.tone ?? "success",
      },
    ]);
  }, []);
  const value = useMemo(() => ({ notify }), [notify]);
  return (
    <ToastContext.Provider value={value}>
      <ToastPrimitive.Provider swipeDirection="down" duration={4500}>
        {children}
        {items.map((item) => (
          <ToastPrimitive.Root
            key={item.id}
            onOpenChange={(open) => {
              if (!open) setItems((prev) => prev.filter((t) => t.id !== item.id));
            }}
            className={clsx(
              "flex items-start gap-3 rounded-2xl border bg-surface p-4 shadow-xl",
              item.tone === "error" ? "border-danger-border" : "border-border",
            )}
          >
            {item.tone === "error" ? (
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-hidden />
            ) : (
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden />
            )}
            <div className="min-w-0 flex-1">
              <ToastPrimitive.Title className="font-medium">{item.title}</ToastPrimitive.Title>
              {item.description ? (
                <ToastPrimitive.Description className="mt-0.5 text-sm text-muted">
                  {item.description}
                </ToastPrimitive.Description>
              ) : null}
            </div>
            <ToastPrimitive.Close aria-label="Dismiss" className="rounded-lg p-1 hover:bg-surface-2">
              <X className="h-4 w-4" />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        ))}
        <ToastPrimitive.Viewport className="fixed bottom-24 left-1/2 z-[60] flex w-[min(420px,calc(100vw-2rem))] -translate-x-1/2 flex-col gap-2 outline-none md:bottom-6" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  return useContext(ToastContext);
}
