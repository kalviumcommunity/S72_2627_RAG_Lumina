import { Component, type ErrorInfo, type ReactNode } from "react";

import { buttonClass } from "../components/ui/Button";

interface State {
  error: Error | null;
}

/**
 * Last line of defence for rendering errors: shows a calm message instead of a blank screen.
 * Keyed by the current path in the shell, so moving to another page recovers.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled rendering error", error, info.componentStack);
  }

  override render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="mx-auto max-w-2xl px-4 py-24">
        <p className="mono-label text-error">Something went wrong</p>
        <h1 className="mt-3 text-section">This page could not be shown.</h1>
        <p className="mt-4 text-lead text-muted">
          Nothing was changed. Reload the page; if it happens again, tell your administrator what you were
          doing.
        </p>
        <button
          type="button"
          className={buttonClass("primary", "md", "mt-8")}
          onClick={() => window.location.reload()}
        >
          Reload
        </button>
      </div>
    );
  }
}
