import { SendHorizontal, Square } from "lucide-react";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

import { Button } from "../../components/ui/Button";

export interface QuestionInputHandle {
  focus: () => void;
}

const MAX = 1000;

/** Large input pinned to the bottom of the screen (one-handed use on a phone). */
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
    // scrollHeight excludes the border; without it the box is 2px short and shows a scrollbar.
    const needed = el.scrollHeight + el.offsetHeight - el.clientHeight;
    el.style.height = `${String(Math.min(needed, 160))}px`;
    el.style.overflowY = needed > 160 ? "auto" : "hidden";
  }, [value]);

  return (
    <form
      className="flex items-end gap-2"
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
        className="max-h-40 min-h-12 flex-1 resize-none rounded-2xl border border-border-strong bg-surface px-4 py-3 text-base shadow-card placeholder:text-muted focus:border-accent focus:outline-none"
        aria-describedby="question-hint"
      />
      {busy ? (
        <Button
          type="button"
          variant="secondary"
          size="icon"
          onClick={onCancel}
          aria-label="Stop"
          className="h-12 w-12 rounded-2xl"
        >
          <Square className="h-4 w-4" />
        </Button>
      ) : (
        <Button
          type="submit"
          size="icon"
          disabled={!value.trim()}
          aria-label="Ask"
          className="h-12 w-12 rounded-2xl"
        >
          <SendHorizontal className="h-5 w-5" />
        </Button>
      )}
    </form>
  );
});
