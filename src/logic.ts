import type { Transaction } from "./types";
export function evaluate(rows: Transaction[], threshold: number) {
  const labeled = rows.filter((r) => r.label !== null);
  const tp = labeled.filter(
    (r) => r.label === 1 && r.score >= threshold,
  ).length;
  const fp = labeled.filter(
    (r) => r.label === 0 && r.score >= threshold,
  ).length;
  const fn = labeled.filter((r) => r.label === 1 && r.score < threshold).length;
  return {
    count: labeled.length,
    tp,
    fp,
    fn,
    tn: labeled.length - tp - fp - fn,
    precision: tp + fp ? tp / (tp + fp) : null,
    recall: tp + fn ? tp / (tp + fn) : null,
  };
}
export const pct = (n: number | null) =>
  n === null ? "—" : `${Math.round(n * 100)}%`;
export const money = (n: number, currency = "USD") =>
  `${new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: currency === "BTC" ? 8 : 2 }).format(n)} ${currency}`;
export const clock = (s: string) => new Date(s).toISOString().slice(11, 16);
