import { describe, expect, it } from "vitest";

import { daysUntil, formatDate, percent, relativeTime, sectionLabel } from "./format";

describe("format", () => {
  it("formats calendar dates without shifting them across timezones", () => {
    expect(formatDate("2026-09-01")).toBe("1 Sept 2026");
    expect(formatDate(null)).toBe("—");
  });

  it("labels clause paths with a section sign and en dashes", () => {
    expect(sectionLabel("4.2")).toBe("§4.2");
    expect(sectionLabel("3-5")).toBe("§3–5");
  });

  it("counts whole days until a date", () => {
    const today = new Date(2026, 8, 30, 9, 0);
    expect(daysUntil("2026-10-02", today)).toBe(2);
    expect(daysUntil("2026-09-25", today)).toBe(-5);
  });

  it("describes recent times relatively", () => {
    const now = Date.parse("2026-09-30T10:00:00Z");
    expect(relativeTime("2026-09-30T09:59:30Z", now)).toBe("just now");
    expect(relativeTime("2026-09-30T09:45:00Z", now)).toBe("15 min ago");
    expect(relativeTime("2026-09-30T07:00:00Z", now)).toBe("3 h ago");
  });

  it("formats fractions as percentages", () => {
    expect(percent(0.125)).toBe("13%");
    expect(percent(0.125, 1)).toBe("12.5%");
  });
});
