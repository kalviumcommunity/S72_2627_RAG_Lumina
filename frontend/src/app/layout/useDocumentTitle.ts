import { useEffect } from "react";

/** Sets the browser tab title ("Library · Lumina") while a page is shown. */
export function useDocumentTitle(title: string | undefined): void {
  useEffect(() => {
    if (!title) return;
    const previous = document.title;
    document.title = `${title} · Lumina`;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
