import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router";

import { ToastProvider } from "../components/ui/Toast";

export function TestProviders({ children, route = "/" }: { children: ReactNode; route?: string }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <TooltipPrimitive.Provider delayDuration={0}>
          <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
        </TooltipPrimitive.Provider>
      </ToastProvider>
    </QueryClientProvider>
  );
}

export function renderWithProviders(ui: ReactElement, route = "/") {
  return render(<TestProviders route={route}>{ui}</TestProviders>);
}
