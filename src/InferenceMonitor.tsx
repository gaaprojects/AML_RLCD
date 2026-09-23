import { useEffect, useState } from "react";
import type { Model } from "./types";
type Sample = {
  id: string;
  score: number;
  label: number | null;
  latency_ms: number;
  at: number;
};
type Status = {
  state: string;
  processed: number;
  total: number;
  errors: number;
  cache_hits: number;
  mean_ms: number | null;
  p95_ms: number | null;
  throughput: number;
  recent: Sample[];
  model: Model;
  last_error: string | null;
};
const percent = (n: number) => `${(n * 100).toFixed(n < 0.001 ? 5 : 2)}%`;
export default function InferenceMonitor({ threshold }: { threshold: number }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const response = await fetch("/api/inference");
        if (!response.ok) throw Error("Monitor unavailable");
        const data = await response.json();
        if (active) {
          setStatus(data);
          setError("");
        }
      } catch {
        if (active) setError("Live monitor disconnected. Reconnecting…");
      }
      if (active) timer = setTimeout(poll, 1000);
    }
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);
  if (!status)
    return (
      <section className="panel monitor-panel">
        {error || "Connecting to inference telemetry…"}
      </section>
    );
  const max = Math.max(1, ...status.recent.map((r) => r.latency_ms));
  const evaluation = status.model.manifest?.evaluation as
    | {
        laya_test?: {
          recall: number;
          precision: number;
          false_alerts: number;
          rows: number;
          positives: number;
        };
      }
    | undefined;
  const test = evaluation?.laya_test;
  return (
    <section className="panel monitor-panel">
      <div className="panel-heading">
        <h2>Live CPU inference</h2>
        <span className="panel-tag">
          {status.state.toUpperCase()} · 1 SECOND REFRESH
        </span>
      </div>
      <p>
        Measured model calls for the current scoring run. Replay playback uses
        existing predictions; it does not run the model again. Cached loads are
        counted separately.
      </p>
      {(error || status.last_error) && (
        <p role="alert" className="error">
          {error || status.last_error}
        </p>
      )}
      <div className="monitor-metrics">
        <article>
          <small>Predictions completed</small>
          <strong>
            {status.processed.toLocaleString()} /{" "}
            {status.total.toLocaleString()}
          </strong>
        </article>
        <article>
          <small>Mean model latency</small>
          <strong>{status.mean_ms?.toFixed(0) ?? "—"} ms</strong>
        </article>
        <article>
          <small>P95 · last 120 calls</small>
          <strong>{status.p95_ms?.toFixed(0) ?? "—"} ms</strong>
        </article>
        <article>
          <small>Model throughput</small>
          <strong>{status.throughput.toFixed(2)} tx/s</strong>
        </article>
      </div>
      <progress
        aria-label="Inference progress"
        max={status.total || 1}
        value={status.processed}
      />
      <p className="muted">
        {status.model.name} · CPU · {status.errors} failed runs ·{" "}
        {status.cache_hits} cached loads · inference time excludes rendering and
        feature extraction
      </p>
      <h3>Latency by completed prediction</h3>
      <svg
        viewBox="0 0 900 180"
        className="latency-chart"
        role="img"
        aria-label="Blue bars show latency in milliseconds for the latest 120 model calls"
      >
        <text x="0" y="15" fill="#aaa">
          {max.toFixed(0)} ms
        </text>
        {status.recent.map((r, i) => (
          <rect
            key={`${r.id}-${r.at}`}
            x={65 + i * 6.8}
            y={155 - (r.latency_ms / max) * 125}
            width="4.5"
            height={(r.latency_ms / max) * 125}
            fill="#69b8ff"
          >
            <title>
              {r.id}: {r.latency_ms.toFixed(1)} ms
            </title>
          </rect>
        ))}
        <text x="0" y="158" fill="#aaa">
          0 ms
        </text>
      </svg>
      <div className="chart-legend">
        <span className="mint-text">Blue bars: model latency</span>
        <span className="amber-text">Amber: score above current threshold</span>
        <span className="muted">Grey: score below threshold</span>
      </div>
      {test && (
        <div className="benchmark-note">
          <strong>
            Exported held-out test results · separate from this replay
          </strong>
          <p>
            {test.rows.toLocaleString()} transactions · {test.positives}{" "}
            laundering labels · recall {percent(test.recall)} · precision{" "}
            {percent(test.precision)} · {test.false_alerts.toLocaleString()}{" "}
            false alerts.
          </p>
          <p>
            This pilot produces many false alerts. The imported replay is an
            early training-period slice, not a new held-out evaluation.
          </p>
        </div>
      )}
      <h3>Latest predictions · threshold {threshold.toExponential(4)}</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Transaction</th>
              <th>Model probability</th>
              <th>Decision</th>
              <th>Dataset label</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            {status.recent
              .slice(-20)
              .reverse()
              .map((r) => (
                <tr key={`${r.id}-${r.at}`}>
                  <td className="mono">{r.id}</td>
                  <td>{percent(r.score)}</td>
                  <td>
                    <span
                      className={`status-badge ${r.score >= threshold ? "alert" : "clear"}`}
                    >
                      {r.score >= threshold ? "Review" : "Below threshold"}
                    </span>
                  </td>
                  <td>
                    {r.label === null
                      ? "Unknown"
                      : r.label
                        ? "Laundering"
                        : "Legitimate"}
                  </td>
                  <td>{r.latency_ms.toFixed(1)} ms</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
