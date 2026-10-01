import { Suspense } from "react";
import { Outlet, useLocation } from "react-router";

import { Skeleton } from "../../components/ui/Skeleton";
import { ErrorBoundary } from "../ErrorBoundary";
import { AnnouncementBar } from "./AnnouncementBar";
import { Footer } from "./Footer";
import { TopNav } from "./TopNav";

function PageFallback() {
  return (
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-10 sm:px-6 lg:px-10" aria-busy="true">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-16 w-2/3" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

/** Frame of every signed-in page: announcement, navigation, the page, the intended-use footer. */
export function AppShell() {
  const { pathname } = useLocation();
  return (
    <div className="flex h-full flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-pill focus:bg-primary focus:px-4 focus:py-2 focus:text-white"
      >
        Skip to content
      </a>
      <AnnouncementBar />
      <TopNav />
      <main id="main" className="min-h-0 flex-1 overflow-y-auto">
        <ErrorBoundary key={pathname}>
          <Suspense fallback={<PageFallback />}>
            <Outlet />
          </Suspense>
        </ErrorBoundary>
      </main>
      <Footer />
    </div>
  );
}
