import * as TabsPrimitive from "@radix-ui/react-tabs";
import { clsx } from "clsx";
import type { ComponentProps } from "react";

export const Tabs = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;

export function TabsList({ className, ...rest }: ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={clsx("inline-flex gap-1 rounded-xl border border-border bg-surface-2 p-1", className)}
      {...rest}
    />
  );
}

export function TabsTrigger({ className, ...rest }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={clsx(
        "inline-flex min-h-10 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-muted",
        "data-[state=active]:bg-surface data-[state=active]:text-text data-[state=active]:shadow-card",
        className,
      )}
      {...rest}
    />
  );
}
