import { useState } from "react";
import { Plus, Trash2, X, Save, ArrowRight } from "lucide-react";
import type { Scenario } from "./types";
type Draft = {
  id: string;
  timestamp: string;
  source: string;
  target: string;
  amount: number;
  currency: string;
  payment_format: string;
};
export default function Editor({
  scenario,
  onClose,
  onSave,
}: {
  scenario: Scenario;
  onClose: () => void;
  onSave: (id: string) => void;
}) {
  const [name, setName] = useState("Untitled investigation");
  const [rows, setRows] = useState<Draft[]>([]);
  const [source, setSource] = useState("ACCOUNT-01"),
    [target, setTarget] = useState("ACCOUNT-02"),
    [amount, setAmount] = useState("10000"),
    [currency, setCurrency] = useState("USD"),
    [time, setTime] = useState("2026-09-22T10:00");
  const [error, setError] = useState(""),
    [saving, setSaving] = useState(false);
  function add(e: React.FormEvent) {
    e.preventDefault();
    if (
      !source.trim() ||
      !target.trim() ||
      !Number.isFinite(+amount) ||
      +amount <= 0
    )
      return;
    setRows([
      ...rows,
      {
        id: crypto.randomUUID(),
        timestamp: new Date(time + "Z").toISOString(),
        source: source.trim(),
        target: target.trim(),
        amount: +amount,
        currency: currency.trim().toUpperCase(),
        payment_format: "Wire",
      },
    ]);
    setTime(
      new Date(new Date(time + "Z").getTime() + 180000)
        .toISOString()
        .slice(0, 16),
    );
  }
  function template(kind: string) {
    const ts = new Date(time + "Z").getTime();
    if (!Number.isFinite(ts)) {
      setError("Enter a valid UTC timestamp before creating a template.");
      return;
    }
    setError("");
    const edges =
      kind === "Cycle"
        ? [
            ["ACCOUNT-01", "ACCOUNT-02"],
            ["ACCOUNT-02", "ACCOUNT-03"],
            ["ACCOUNT-03", "ACCOUNT-01"],
          ]
        : kind === "Fan-in"
          ? [
              ["ACCOUNT-01", "HUB"],
              ["ACCOUNT-02", "HUB"],
              ["ACCOUNT-03", "HUB"],
              ["HUB", "EXIT"],
            ]
          : [
              ["ORIGIN", "ACCOUNT-01"],
              ["ACCOUNT-01", "ACCOUNT-02"],
              ["ACCOUNT-02", "EXIT"],
            ];
    setRows(
      edges.map(([source, target], i) => ({
        id: crypto.randomUUID(),
        timestamp: new Date(ts + i * 180000).toISOString(),
        source,
        target,
        amount: 10000 - i * 100,
        currency: "USD",
        payment_format: "Wire",
      })),
    );
    setName(`${kind} exploration`);
  }
  async function save() {
    setSaving(true);
    setError("");
    try {
      const res = await fetch("/api/scenarios", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: "User-authored scenario · unlabeled",
          transactions: rows,
        }),
      });
      if (!res.ok) {
        const body = await res.json();
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : "Check the scenario fields and transaction limits.",
        );
      }
      const data = await res.json();
      onSave(data.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="modal-backdrop">
      <section
        className="editor"
        role="dialog"
        aria-modal="true"
        aria-label="Scenario editor"
      >
        <header>
          <div>
            <span className="eyebrow">SIMULATION LAB</span>
            <h2>Build an investigation</h2>
          </div>
          <button onClick={onClose} aria-label="Close scenario editor">
            <X size={19} />
          </button>
        </header>
        <p className="muted">
          Create connected transfers. Accounts appear automatically when first
          used. Custom scenarios carry no ground-truth labels.
        </p>
        <label className="field">
          Scenario name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={80}
          />
        </label>
        <div className="template-row">
          <span>Start from</span>
          {["Chain", "Cycle", "Fan-in"].map((t) => (
            <button key={t} onClick={() => template(t)}>
              {t}
            </button>
          ))}
          <button
            onClick={() => {
              setRows(
                scenario.transactions.map(
                  ({
                    id,
                    timestamp,
                    source,
                    target,
                    amount,
                    currency,
                    payment_format,
                  }) => ({
                    id,
                    timestamp,
                    source,
                    target,
                    amount,
                    currency,
                    payment_format,
                  }),
                ),
              );
              setName(`${scenario.name.slice(0, 65)} / copy`);
            }}
          >
            Current scenario
          </button>
        </div>
        <form onSubmit={add} className="transaction-form">
          <label className="field">
            From account
            <input
              required
              value={source}
              maxLength={100}
              onChange={(e) => setSource(e.target.value)}
            />
          </label>
          <ArrowRight size={16} />
          <label className="field">
            To account
            <input
              required
              value={target}
              maxLength={100}
              onChange={(e) => setTarget(e.target.value)}
            />
          </label>
          <label className="field">
            Amount
            <input
              type="number"
              required
              min="0.01"
              max="1000000000000000"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </label>
          <label className="field">
            Currency
            <input
              required
              minLength={2}
              maxLength={30}
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
            />
          </label>
          <label className="field">
            Timestamp · UTC
            <input
              type="datetime-local"
              required
              value={time}
              onChange={(e) => setTime(e.target.value)}
            />
          </label>
          <button className="primary" disabled={rows.length >= 2000}>
            <Plus size={15} />
            Add transfer
          </button>
        </form>
        <div className="draft-rows">
          {!rows.length ? (
            <div className="empty">
              Add your first transfer or choose a scenario template.
            </div>
          ) : (
            rows.map((r, i) => (
              <div className="draft-row" key={r.id}>
                <span className="mono muted">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span>
                  {r.source} <span className="muted">→</span> {r.target}
                </span>
                <span className="mono">
                  {r.amount.toLocaleString()} {r.currency}
                </span>
                <span className="muted">{r.timestamp.slice(11, 16)} UTC</span>
                <button
                  aria-label={`Remove transfer ${i + 1}`}
                  onClick={() => setRows(rows.filter((x) => x.id !== r.id))}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>
        {error && <div className="error">{error}</div>}
        <footer>
          <span className="muted">
            {rows.length} / 2,000 transfers · stored on this computer
          </span>
          <button
            className="primary"
            disabled={!rows.length || !name.trim() || saving}
            onClick={save}
          >
            <Save size={15} />
            {saving ? "Saving…" : "Save & investigate"}
          </button>
        </footer>
      </section>
    </div>
  );
}
