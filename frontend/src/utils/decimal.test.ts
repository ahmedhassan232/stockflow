import { describe, expect, it } from "vitest";
import { linePreview, parse, toFixed } from "./decimal";

const line = (...args: Parameters<typeof linePreview>) => {
  const l = linePreview(...args);
  return [toFixed(l.gross), toFixed(l.discount), toFixed(l.tax), toFixed(l.total)];
};

describe("decimal preview maths (must match backend app/modules/sales/calc.py)", () => {
  it("rounds half up without float error", () => {
    expect(toFixed(parse("1.005"))).toBe("1.01"); // Number(1.005).toFixed(2) === "1.00"
    expect(toFixed(parse("0.1") + parse("0.2"))).toBe("0.30");
    expect(toFixed(parse("2.675"))).toBe("2.68");
  });
  it("computes the same lines as the backend tests", () => {
    expect(line("2", "100.00", "14", "10.00")).toEqual(["200.00", "10.00", "26.60", "216.60"]);
    expect(line("1.500", "9.99", "0")).toEqual(["14.99", "0.00", "0.00", "14.99"]);
    expect(line("2.500", "3.3333", "0")).toEqual(["8.33", "0.00", "0.00", "8.33"]);
  });
  it("treats junk as zero", () => {
    expect(toFixed(parse("abc"))).toBe("0.00");
    expect(toFixed(parse(""))).toBe("0.00");
  });
});
