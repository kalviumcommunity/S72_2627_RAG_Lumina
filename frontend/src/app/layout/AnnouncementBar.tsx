import { X } from "lucide-react";
import { useState } from "react";

const KEY = "lumina.announcement.dismissed";

function wasDismissed(): boolean {
  try {
    return sessionStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** Black strip above the navigation. States that the demo documents are synthetic. */
export function AnnouncementBar() {
  const [hidden, setHidden] = useState(wasDismissed);
  if (hidden) return null;
  const dismiss = () => {
    setHidden(true);
    try {
      sessionStorage.setItem(KEY, "1");
    } catch {
      /* storage unavailable: hide for this page view only */
    }
  };
  return (
    <div
      role="region"
      aria-label="Announcement"
      className="relative flex min-h-9 items-center justify-center bg-black px-12 py-2 text-center text-micro text-white"
    >
      <p>
        Demo environment — every document is synthetic and none of it is clinical guidance.{" "}
        <a href="#intended-use" className="text-white underline underline-offset-2">
          Intended use
        </a>
      </p>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Dismiss announcement"
        className="absolute right-3 inline-flex h-7 w-7 items-center justify-center rounded-full hover:bg-white/15"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
