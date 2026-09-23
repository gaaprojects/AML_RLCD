import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import Graph from "./Graph";
import { money } from "./logic";
import type { Transaction } from "./types";
describe("source transaction graph", () => {
  it("preserves cents and separates repeated and reverse transfers", () => {
    const base = {
      timestamp: "2022-09-01T00:00:00Z",
      amount: 123.45,
      currency: "USD",
      payment_format: "ACH",
      label: 0 as const,
      score: 0.01,
      reasons: [],
      features: {},
    };
    const rows: Transaction[] = [
      { ...base, id: "one", source: "A", target: "B" },
      { ...base, id: "two", source: "A", target: "B" },
      { ...base, id: "three", source: "B", target: "A" },
    ];
    const html = renderToStaticMarkup(
      <Graph
        rows={rows}
        account="A"
        selected="one"
        path={[]}
        threshold={0.5}
        onAccount={() => {}}
        onTransaction={() => {}}
      />,
    );
    const paths = [...html.matchAll(/<path d="([^"]+)" class="edge-hit"/g)].map(
      (m) => m[1],
    );
    expect(paths).toHaveLength(3);
    expect(new Set(paths).size).toBe(3);
    expect(html).toContain("123.45 USD");
    expect(html).toContain("2022-09-01T00:00:00Z");
    expect(money(123.45, "USD")).toBe("123.45 USD");
  });
});
