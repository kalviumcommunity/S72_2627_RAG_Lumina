import * as TabsPrimitive from "@radix-ui/react-tabs";
import { clsx } from "clsx";
import type { ComponentProps } from "react";

export const Tabs = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;

/** Tabs rendered as outlined filter pills; the selected pill fills near-black. */
export function TabsList({ className, ...rest }: ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={clsx("flex flex-wrap gap-2", className)} {...rest} />;
}

export function TabsTrigger({ className, ...rest }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={clsx(
        "inline-flex min-h-9 items-center whitespace-nowrap rounded-xl border border-hairline px-4 text-sm text-ink",
        "transition-colors hover:border-primary",
        "data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-white",
        className,
      )}
      {...rest}
    />
  );
}
