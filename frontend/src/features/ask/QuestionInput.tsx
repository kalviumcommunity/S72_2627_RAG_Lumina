import { ArrowUp, Square } from "lucide-react";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

export interface QuestionInputHandle {
  focus: () => void;
}

const MAX = 1000;

/** Composer pinned to the bottom of the screen (one-handed use on a phone). Enter sends. */
export const QuestionInput = forwardRef<
  QuestionInputHandle,
  { value: string; onChange: (v: string) => void; onSubmit: () => void; onCancel: () => void; busy: boolean }
>(function QuestionInput({ value, onChange, onSubmit, onCancel, busy }, ref) {
  const area = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => ({
    focus: () => {
      area.current?.focus();
      const len = area.current?.value.length ?? 0;
      area.current?.setSelectionRange(len, len);
    },
  }));
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    const needed = el.scrollHeight;
    el.style.height = `${String(Math.min(needed, 160))}px`;
    el.style.overflowY = needed > 160 ? "auto" : "hidden";
  }, [value]);

  return (
    <form
      className="flex items-end gap-2 rounded-md border border-hairline bg-canvas p-2 pl-4 transition-colors focus-within:border-primary"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label htmlFor="question" className="sr-only">
        Ask about an approved protocol, drug guideline or circular
      </label>
      <textarea
        id="question"
        ref={area}
        rows={1}
        maxLength={MAX}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            onSubmit();
          }
        }}
        placeholder="Ask about a protocol, drug guideline or circular…"
        className="max-h-40 min-h-10 flex-1 resize-none bg-transparent py-2 text-base text-ink placeholder:text-muted focus:outline-none"
        aria-describedby="question-hint"
      />
      {busy ? (
        <button
          type="button"
          onClick={onCancel}
          aria-label="Stop"
          className="inline-flex min-h-10 items-center gap-2 rounded-pill border border-primary px-4 text-sm font-medium hover:bg-primary hover:text-white"
        >
          <Square className="h-3.5 w-3.5" aria-hidden />
          <span className="hidden sm:inline">Stop</span>
        </button>
      ) : (
        <button
          type="submit"
          disabled={!value.trim()}
          aria-label="Ask"
          className="inline-flex min-h-10 items-center gap-2 rounded-pill bg-primary px-5 text-sm font-medium text-white hover:bg-primary-hover disabled:opacity-30"
        >
          <span className="hidden sm:inline">Ask</span>
          <ArrowUp className="h-4 w-4" aria-hidden />
        </button>
      )}
    </form>
  );
});
