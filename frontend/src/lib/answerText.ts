/**
 * Answer text → renderable segments.
 *
 * The server returns plain text where every verified sentence ends with markers like [S1] or
 * [S2][S4]. Markers become clickable citation chips; "- " / "• " / "1. " lines become list items.
 */

export type Segment = { kind: "text"; text: string } | { kind: "cite"; marker: string };

export interface AnswerLine {
  bullet: boolean;
  segments: Segment[];
}

const MARKER = /\[(S\d+)\]/g;
const BULLET = /^\s*(?:[-*•]|\d{1,2}[.)])\s+/;

export function parseSegments(text: string): Segment[] {
  const segments: Segment[] = [];
  let cursor = 0;
  for (const match of text.matchAll(MARKER)) {
    const index = match.index;
    if (index > cursor) segments.push({ kind: "text", text: text.slice(cursor, index) });
    segments.push({ kind: "cite", marker: match[1] ?? "" });
    cursor = index + match[0].length;
  }
  if (cursor < text.length) segments.push({ kind: "text", text: text.slice(cursor) });
  return segments;
}

export function parseAnswer(answer: string): AnswerLine[] {
  return answer
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0)
    .map((line) => {
      const bullet = BULLET.test(line);
      return { bullet, segments: parseSegments(bullet ? line.replace(BULLET, "") : line.trim()) };
    });
}

/** Markers in order of first appearance (used to order the citation list). */
export function markersInOrder(answer: string): string[] {
  return [...new Set([...answer.matchAll(MARKER)].map((m) => m[1] ?? ""))].filter(Boolean);
}
