export type Transaction = {
  id: string;
  timestamp: string;
  source: string;
  target: string;
  amount: number;
  currency: string;
  payment_format: string;
  label: 0 | 1 | null;
  score: number;
  reasons: string[];
  features: Record<string, number>;
};
export type Model = {
  mode: "rules" | "laya";
  name: string;
  error: string | null;
  manifest: Record<string, unknown> | null;
  default_threshold: number;
};
export type Scenario = {
  id: string;
  name: string;
  description: string;
  origin: "demo" | "custom" | "ibm";
  transactions: Transaction[];
  model: Model;
};
export type PathResult = {
  transaction_ids: string[];
  accounts: string[];
  pattern: string;
};
