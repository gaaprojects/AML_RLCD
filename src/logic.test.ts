import { describe, it, expect } from "vitest";
import { evaluate } from "./logic";
import type { Transaction } from "./types";
const rows = [
  { score: 0.5, label: 1 },
  { score: 0.8, label: 0 },
  { score: 0.1, label: 1 },
  { score: 0.99, label: null },
] as Transaction[];
describe("threshold analysis", () => {
  it("excludes unlabeled rows and includes the boundary", () => {
    expect(evaluate(rows, 0.5)).toEqual({
      count: 3,
      tp: 1,
      fp: 1,
      fn: 1,
      tn: 0,
      precision: 0.5,
      recall: 0.5,
    });
  });
  it("raising threshold never increases alerts", () => {
    let last = Infinity;
    for (let t = 0; t <= 1; t += 0.01) {
      const m = evaluate(rows, t);
      expect(m.tp + m.fp).toBeLessThanOrEqual(last);
      last = m.tp + m.fp;
    }
  });
  it("does not manufacture metrics without labels", () => {
    expect(
      evaluate([{ score: 0.9, label: null }] as Transaction[], 0.5).precision,
    ).toBeNull();
    expect(evaluate([], 0).recall).toBeNull();
  });
});
