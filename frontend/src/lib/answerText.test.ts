import { describe, expect, it } from "vitest";

import { markersInOrder, parseAnswer, parseSegments } from "./answerText";

describe("parseSegments", () => {
  it("splits text and citation markers in order", () => {
    expect(parseSegments("Hold for 1 hour [S1] then restart [S2][S3].")).toEqual([
      { kind: "text", text: "Hold for 1 hour " },
      { kind: "cite", marker: "S1" },
      { kind: "text", text: " then restart " },
      { kind: "cite", marker: "S2" },
      { kind: "cite", marker: "S3" },
      { kind: "text", text: "." },
    ]);
  });

  it("returns plain text when there are no markers", () => {
    expect(parseSegments("No markers here")).toEqual([{ kind: "text", text: "No markers here" }]);
  });

  it("ignores bracketed text that is not a source marker", () => {
    expect(parseSegments("aPTT [seconds] [S1]")).toEqual([
      { kind: "text", text: "aPTT [seconds] " },
      { kind: "cite", marker: "S1" },
    ]);
  });
});

describe("parseAnswer", () => {
  it("recognises dash, bullet and numbered list lines", () => {
    const lines = parseAnswer("Intro line [S1]\n- first [S1]\n• second [S2]\n3. third [S2]\n\n");
    expect(lines.map((l) => l.bullet)).toEqual([false, true, true, true]);
    expect(lines[1]?.segments[0]).toEqual({ kind: "text", text: "first " });
    expect(lines[3]?.segments[0]).toEqual({ kind: "text", text: "third " });
  });

  it("handles Windows line endings and drops blank lines", () => {
    expect(parseAnswer("a [S1]\r\n\r\nb [S2]")).toHaveLength(2);
  });
});

describe("markersInOrder", () => {
  it("lists each marker once, by first appearance", () => {
    expect(markersInOrder("x [S2] y [S1] z [S2][S3]")).toEqual(["S2", "S1", "S3"]);
  });
});
