const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function parse(value: string): Date {
  // Plain dates ("2026-09-01") are calendar dates: never shift them by the local timezone.
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00`) : new Date(value);
}

export function formatDate(value: string | null | undefined): string {
  return value ? DATE.format(parse(value)) : "—";
}

export function formatDateTime(value: string | null | undefined): string {
  return value ? DATE_TIME.format(parse(value)) : "—";
}

export function daysUntil(value: string, today = new Date()): number {
  const target = parse(value);
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 12);
  return Math.round((target.getTime() - start.getTime()) / 86_400_000);
}

export function relativeTime(value: string, now = Date.now()): string {
  const seconds = Math.round((now - new Date(value).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return formatDate(value);
}

export function sectionLabel(path: string): string {
  return `§${path.replace(/-/g, "–")}`;
}

export function percent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatLatencyMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

export const formatIsoDate = formatDate;
export const formatIsoTime = formatDateTime;
