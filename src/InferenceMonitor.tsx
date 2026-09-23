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
  elapsed_seconds: number;
  remaining_seconds: number | null;
  total_ms: number;
  resources: {
    process_cpu_percent: number;
    rss_mb: number;
    peak_rss_mb: number;
    system_ram_percent: number;
    available_ram_mb: number;
    cpu_seconds: number;
    threads: number;
    logical_cpus: number;
    device: string;
  };
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
  const r = status.resources;
  const duration = (seconds: number | null) =>
    seconds === null
      ? "—"
      : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  const alerts = status.recent.filter((row) => row.score >= threshold);
  const labeled = status.recent.filter((row) => row.label !== null);
  const fp = alerts.filter((row) => row.label === 0).length;
  const tp = alerts.filter((row) => row.label === 1).length;
  const positives = labeled.filter((row) => row.label === 1).length;
  const bins = [0, 0.00001, 0.0001, 0.001, 0.01, 0.1, 1];
  const counts = bins
    .slice(0, -1)
    .map(
      (low, i) =>
        status.recent.filter(
          (row) =>
            row.score >= low &&
            (i === bins.length - 2
              ? row.score <= bins[i + 1]
              : row.score < bins[i + 1]),
        ).length,
    );
  const largest = Math.max(1, ...counts);
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
      <h3>Time and resource consumption</h3>
      <div className="monitor-metrics">
        <article>
          <small>Run elapsed · wall clock</small>
          <strong>{duration(status.elapsed_seconds)}</strong>
        </article>
        <article>
          <small>Total model-call time</small>
          <strong>{duration(status.total_ms / 1000)}</strong>
        </article>
        <article>
          <small>Estimated time remaining</small>
          <strong>{duration(status.remaining_seconds)}</strong>
        </article>
        <article>
          <small>Server CPU · machine capacity</small>
          <strong>{r.process_cpu_percent.toFixed(1)}%</strong>
        </article>
        <article>
          <small>Server resident RAM</small>
          <strong>{r.rss_mb.toFixed(0)} MB</strong>
        </article>
        <article>
          <small>Peak server resident RAM</small>
          <strong>{r.peak_rss_mb.toFixed(0)} MB</strong>
        </article>
        <article>
          <small>System RAM used</small>
          <strong>{r.system_ram_percent.toFixed(1)}%</strong>
        </article>
        <article>
          <small>System RAM available</small>
          <strong>{(r.available_ram_mb / 1024).toFixed(2)} GB</strong>
        </article>
      </div>
      <p className="muted">
        {r.device} inference · {r.logical_cpus} logical processors · {r.threads}{" "}
        server threads · {r.cpu_seconds.toFixed(1)} CPU seconds since server
        startup. CPU is normalized to total machine capacity. RAM includes the
        model and API process. Remaining time is an estimate from average model
        latency. Power draw and energy consumption are not measured.
      </p>
      <h3>Prediction behavior · latest {status.recent.length} model calls</h3>
      <div className="monitor-metrics">
        <article>
          <small>Alert rate · current threshold</small>
          <strong>
            {status.recent.length
              ? percent(alerts.length / status.recent.length)
              : "—"}
          </strong>
        </article>
        <article>
          <small>False alerts · known labels</small>
          <strong>{fp}</strong>
        </article>
        <article>
          <small>Precision · known labels</small>
          <strong>{tp + fp ? percent(tp / (tp + fp)) : "—"}</strong>
        </article>
        <article>
          <small>Recall · known labels</small>
          <strong>{positives ? percent(tp / positives) : "—"}</strong>
        </article>
      </div>
      <p className="muted">
        Rolling window only; {labeled.length} labeled predictions and{" "}
        {positives} positives. A dash means the metric has no applicable
        observations. These are replay observations, not independent test
        results.
      </p>
      <h3>Score distribution · probability ranges</h3>
      <div
        className="score-distribution"
        role="img"
        aria-label="Distribution of probabilities for the latest 120 predictions"
      >
        {counts.map((count, i) => (
          <div key={i}>
            <span>
              {bins[i].toExponential(0)} – {bins[i + 1].toExponential(0)}
            </span>
            <div>
              <i style={{ width: `${(count / largest) * 100}%` }} />
            </div>
            <b>{count}</b>
          </div>
        ))}
      </div>
      <p className="muted">
        Purple bars count predictions in each range; ranges use unequal widths
        on the probability scale. Alert decisions use the exact threshold above.
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
