import { useEffect, useMemo, useState, useRef } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Box,
  Check,
  ChevronRight,
  Database,
  Download,
  FlaskConical,
  GitBranch,
  Layers,
  Network,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Search,
  Settings2,
  Shield,
  SkipForward,
  SlidersHorizontal,
  Target,
  X,
} from "lucide-react";
import Graph from "./Graph";
import Editor from "./Editor";
import InferenceMonitor from "./InferenceMonitor";
import { clock, evaluate, money, pct } from "./logic";
import type { PathResult, Scenario } from "./types";
export default function App() {
  const [scenario, setScenario] = useState<Scenario | null>(null),
    [sid, setSid] = useState("default"),
    [list, setList] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [threshold, setThreshold] = useState(0.35),
    [visible, setVisible] = useState(46),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1);
  const [account, setAccount] = useState("HARBOR-02"),
    [selected, setSelected] = useState(""),
    [tab, setTab] = useState("Investigation"),
    [filter, setFilter] = useState("all"),
    [query, setQuery] = useState(""),
    [editor, setEditor] = useState(false),
    [paths, setPaths] = useState<PathResult[]>([]),
    [path, setPath] = useState<string[]>([]),
    [pathsRequested, setPathsRequested] = useState(false),
    [pathError, setPathError] = useState(""),
    [busyPaths, setBusyPaths] = useState(false);
  const [toast, setToast] = useState("");
  const [run, setRun] = useState(0);
  const [inferenceTotal, setInferenceTotal] = useState(0);
  const [cached, setCached] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [stopping, setStopping] = useState(false);
  const inferenceRun = useRef("");
  async function stopWork() {
    setPlaying(false);
    if (!loading || !inferenceRun.current) return;
    setStopping(true);
    try {
      const response = await fetch(
        `/api/inference/${inferenceRun.current}/stop`,
        { method: "POST" },
      );
      if (!response.ok) throw Error("Unable to stop inference");
    } catch {
      setToast("Stop request failed. Please try again.");
      setStopping(false);
    }
  }
  const activeContext = useRef("");
  activeContext.current = `${sid}:${visible}:${account}`;
  useEffect(() => {
    let current = true;
    setLoading(true);
    setError("");
    setPlaying(false);
    setCached(false);
    setStopped(false);
    setStopping(false);
    inferenceRun.current = "";
    setScenario(null);
    setVisible(0);
    fetch("/api/scenarios")
      .then((r) => r.json())
      .then((l) => current && setList(l));
    const stream = new EventSource(
      `/api/scenarios/${sid}/stream?fresh=${run > 0}`,
    );
    stream.addEventListener("meta", (event) => {
      if (!current) return;
      const s = JSON.parse((event as MessageEvent).data);
      inferenceRun.current = s.run_id;
      setScenario(s);
      setInferenceTotal(s.total);
      setThreshold(s.model.default_threshold);
      setAccount("");
      setSelected("");
      setPaths([]);
      setPath([]);
      setPathsRequested(false);
    });
    stream.addEventListener("rows", (event) => {
      if (!current) return;
      const batch = JSON.parse((event as MessageEvent).data);
      setScenario((s) =>
        s ? { ...s, transactions: [...s.transactions, ...batch] } : s,
      );
      setVisible((n) => n + batch.length);
      setAccount((a) => a || batch[0]?.source || "");
      setSelected((a) => a || batch[0]?.id || "");
    });
    stream.addEventListener("stopped", () => {
      if (!current) return;
      setStopped(true);
      setStopping(false);
      setLoading(false);
      setPlaying(false);
      stream.close();
    });
    stream.addEventListener("complete", (event) => {
      if (!current) return;
      setCached(JSON.parse((event as MessageEvent).data).cached);
      setLoading(false);
      stream.close();
    });
    stream.addEventListener("failure", (event) => {
      if (!current) return;
      setError(JSON.parse((event as MessageEvent).data).detail);
      setLoading(false);
      stream.close();
    });
    stream.onerror = () => {
      if (current) {
        setError(
          "Inference connection interrupted. Reconnect to retry; check local model status.",
        );
        setLoading(false);
      }
      stream.close();
    };
    return () => {
      current = false;
      if (inferenceRun.current)
        fetch(`/api/inference/${inferenceRun.current}/stop`, {
          method: "POST",
        }).catch(() => {});
      stream.close();
    };
  }, [sid, run]);
  useEffect(() => {
    if (!playing || !scenario) return;
    const id = setInterval(
      () =>
        setVisible((n) => {
          if (n >= scenario.transactions.length) {
            setPlaying(false);
            return n;
          }
          return n + 1;
        }),
      1000 / speed,
    );
    return () => clearInterval(id);
  }, [playing, speed, scenario]);
  useEffect(() => {
    setPaths([]);
    setPath([]);
    setPathsRequested(false);
    setPathError("");
  }, [account, visible, sid]);
  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(""), 3500);
    return () => clearTimeout(id);
  }, [toast]);
  const rows = useMemo(
    () => scenario?.transactions.slice(0, visible) || [],
    [scenario, visible],
  );
  const alerts = rows.filter((r) => r.score >= threshold),
    stats = evaluate(rows, threshold),
    accounts = [...new Set(rows.flatMap((r) => [r.source, r.target]))];
  const tx = rows.find((r) => r.id === selected),
    related = rows.filter((r) => r.source === account || r.target === account),
    risk = Math.max(0, ...related.map((r) => r.score));
  const displayed = rows
    .filter(
      (r) =>
        (filter !== "alerts" || r.score >= threshold) &&
        (filter !== "account" ||
          r.source === account ||
          r.target === account) &&
        `${r.id} ${r.source} ${r.target}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    )
    .slice()
    .reverse();
  function selectTx(id: string) {
    setSelected(id);
    const r = rows.find((r) => r.id === id);
    if (r) setAccount(r.source);
  }
  async function trace() {
    const context = activeContext.current;
    setBusyPaths(true);
    setPathError("");
    try {
      const res = await fetch(
        `/api/scenarios/${sid}/paths?account=${encodeURIComponent(account)}&visible=${visible}`,
      );
      if (!res.ok) throw Error("Unable to trace paths");
      const d = await res.json();
      if (activeContext.current !== context) return;
      setPaths(d.paths);
      setPath(d.paths[0]?.transaction_ids || []);
      setPathsRequested(true);
    } catch (e) {
      setPathError(String(e));
    } finally {
      setBusyPaths(false);
    }
  }
  function exportCase() {
    const blob = new Blob(
      [
        JSON.stringify(
          {
            scenario: scenario?.name,
            account,
            threshold,
            model: scenario?.model,
            transactions: related,
            paths,
            note: "Investigation evidence; connected transfers do not prove fund identity.",
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `investigation-${account}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setToast("Investigation exported");
  }
  if (loading && !scenario)
    return (
      <div className="loading">
        <div className="brand-mark">
          <Network />
        </div>
        <h2>TRACE</h2>
        <p>Preparing the local investigation workspace…</p>
      </div>
    );
  if (error)
    return (
      <div className="loading">
        <Shield size={40} />
        <h2>Workspace unavailable</h2>
        <p className="error">{error}</p>
        <button onClick={() => location.reload()}>Reconnect</button>
      </div>
    );
  if (!scenario) return null;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="Trace home">
          <div className="brand-mark">
            <Network size={23} />
          </div>
          <span>
            TRACE<small>TRANSACTION ANALYSIS</small>
          </span>
        </a>
        <div className="workspace-label">
          WORKSPACE <span>LOCAL</span>
        </div>
        <div className="workspace-card">
          <div className="workspace-icon">
            <Box size={17} />
          </div>
          <div>
            AML Research<small>Personal workspace</small>
          </div>
        </div>
        <div className="nav-label">OPERATIONS</div>
        <nav>
          {[
            { name: "Investigation", icon: Network },
            { name: "Transactions", icon: Layers },
            { name: "Evaluation", icon: Activity },
            { name: "Inference monitor", icon: Target },
            { name: "Model & data", icon: Database },
          ].map(({ name, icon: Icon }) => (
            <button
              className={tab === name ? "active" : ""}
              key={name}
              onClick={() => setTab(name)}
            >
              <Icon size={17} />
              {name}
              {name === "Investigation" && (
                <span className="nav-count">{alerts.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-case">
          <span className="nav-label">ACTIVE INVESTIGATION</span>
          <div>
            <span className="dot mint" /> {scenario.name}
          </div>
          <small>{rows.length} observed transactions</small>
        </div>
        <div className="sidebar-bottom">
          <span className="local-status">
            <i className="dot mint" /> Local environment
          </span>
          <small>Offline · data stays on this device</small>
          <div className="profile">
            <div className="avatar">AN</div>
            <div>
              Analyst<small>Research & simulation</small>
            </div>
            <Shield size={16} />
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} /> AML Research{" "}
            <ChevronRight size={13} />
            <span>{tab}</span>
          </div>
          <div className="topbar-right">
            <span className="connection">
              <i className="dot mint" /> LOCAL SESSION
            </span>
            <span className="version">v0.1</span>
          </div>
        </header>
        <div className="inference-banner" role="status">
          <span>
            <i className={`dot ${loading ? "amber" : "mint"}`} />{" "}
            {stopping
              ? "Stopping after current prediction"
              : stopped
                ? "Inference stopped"
                : loading
                  ? "Live inference"
                  : cached
                    ? "Cached predictions"
                    : "Inference complete"}{" "}
            · {scenario.transactions.length.toLocaleString()} /{" "}
            {inferenceTotal.toLocaleString()} transactions ·{" "}
            {scenario.origin === "ibm"
              ? "IBM synthetic dataset"
              : scenario.origin}
          </span>
          <button
            disabled={stopping || (!loading && !playing)}
            onClick={stopWork}
          >
            {stopping ? "Stopping…" : "Stop mapping & inference"}
          </button>
          <button onClick={() => setTab("Inference monitor")}>
            View inference monitor
          </button>
          <button disabled={loading} onClick={() => setRun((n) => n + 1)}>
            Run inference again
          </button>
        </div>
        <div className="page-heading">
          <div>
            <div className="eyebrow">
              CASE WORKSPACE <span>/</span> TRANSACTION ANALYSIS
            </div>
            <h1>
              {tab === "Investigation"
                ? "Investigation"
                : tab === "Transactions"
                  ? "Transactions"
                  : tab === "Evaluation"
                    ? "Evaluation"
                    : tab === "Inference monitor"
                      ? "Inference monitor"
                      : "Model & data"}
            </h1>
            <p>
              {tab === "Investigation"
                ? "Review transfers, inspect accounts and trace connected activity."
                : tab === "Evaluation"
                  ? "Explore the balance between detection coverage and alert workload."
                  : tab === "Transactions"
                    ? "Every observed transfer, connected to its investigation context."
                    : "A transparent, local pipeline from Colab training to offline decisions."}
            </p>
          </div>
          <button className="primary" onClick={() => setEditor(true)}>
            <Plus size={16} />
            New scenario
          </button>
        </div>
        <div className="simulation-bar">
          <div className="scenario-select">
            <span className="label">SCENARIO</span>
            <select
              aria-label="Active scenario"
              value={sid}
              onChange={(e) => setSid(e.target.value)}
            >
              {sid === "default" && (
                <option value="default">{scenario.name}</option>
              )}
              {list.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <span className="demo-badge">
            {scenario.origin === "demo"
              ? "SYNTHETIC DEMO"
              : scenario.origin === "ibm"
                ? "IBM DATASET"
                : "CUSTOM · UNLABELED"}
          </span>
          <div className="replay-controls">
            <button
              aria-label="Reset replay"
              disabled={loading}
              onClick={() => {
                setPlaying(false);
                setVisible(0);
              }}
            >
              <RotateCcw size={15} />
            </button>
            <button
              className="play-button"
              disabled={loading}
              aria-label={playing ? "Pause replay" : "Play replay"}
              onClick={() => {
                if (visible >= scenario.transactions.length) setVisible(0);
                setPlaying(!playing);
              }}
            >
              {playing ? <Pause size={14} /> : <Play size={14} />}
            </button>
            <button
              aria-label="Next transaction"
              disabled={loading || visible >= scenario.transactions.length}
              onClick={() =>
                setVisible((n) => Math.min(n + 1, scenario.transactions.length))
              }
            >
              <SkipForward size={15} />
            </button>
            <select
              aria-label="Replay speed"
              value={speed}
              onChange={(e) => setSpeed(+e.target.value)}
            >
              <option value={1}>1×</option>
              <option value={4}>4×</option>
              <option value={10}>10×</option>
            </select>
            <span className="mono replay-count">
              {visible} / {scenario.transactions.length}
            </span>
            <span className="muted replay-status">
              {loading ? "SCORING LIVE" : playing ? "REPLAYING" : "PAUSED"}
            </span>
          </div>
        </div>
        {scenario.origin === "ibm" && (
          <div className="dataset-note">
            <strong>IBM synthetic transaction records</strong>
            <span>
              {rows.length.toLocaleString()} observed transfers ·{" "}
              {rows
                .filter((r) => r.source === r.target)
                .length.toLocaleString()}{" "}
              self-transfers · {rows.filter((r) => r.label === 1).length}{" "}
              laundering labels. Self-transfers are hidden from the graph;
              separate curves represent repeated transfers. Paths require
              increasing timestamps and the same currency. Accounts outside the
              selected neighborhood are not shown.
            </span>
          </div>
        )}
        <div className="metrics-grid">
          <div className="metric">
            <span>
              OBSERVED TRANSFERS <Layers size={15} />
            </span>
            <strong>
              {rows.length.toLocaleString()}
              <small>transactions</small>
            </strong>
            <p>
              <span className="mint-text">{accounts.length}</span> connected
              accounts
            </p>
          </div>
          <div className="metric">
            <span>
              FLAGGED ACTIVITY <Shield size={15} />
            </span>
            <strong className="amber-text">
              {alerts.length}
              <small>above threshold</small>
            </strong>
            <p>
              {rows.length
                ? Math.round((alerts.length / rows.length) * 100)
                : 0}
              % of observed transfers
            </p>
          </div>
          <div className="metric">
            <span>
              DETECTION RECALL <Target size={15} />
            </span>
            <strong>
              {pct(stats.recall)}
              <small>
                {stats.count ? "labeled observations" : "labels unavailable"}
              </small>
            </strong>
            <p>
              {stats.count
                ? `${stats.fn} missed positives${sid === "demo" ? " · demo only" : ""}`
                : "Ground truth unavailable"}
            </p>
          </div>
          <div className="metric">
            <span>
              FALSE ALERTS <Activity size={15} />
            </span>
            <strong>
              {stats.count ? stats.fp : "—"}
              <small>
                {stats.count ? "labeled negatives flagged" : "not measurable"}
              </small>
            </strong>
            <p>{pct(stats.precision)} precision on labeled observations</p>
          </div>
        </div>
        <div className="model-notice">
          <FlaskConical size={14} />
          <span>
            {scenario.model.mode === "rules" ? (
              <>
                Demonstration rules active. Scores are{" "}
                <b>not Laya predictions or calibrated probabilities.</b> Load a
                trained checkpoint to enable model inference.
              </>
            ) : (
              <>
                Laya AML checkpoint active. Evidence indicators are separate
                rules; account scores are heuristic aggregates.
              </>
            )}
          </span>
          <button onClick={() => setTab("Model & data")}>
            Model details <ArrowRight size={13} />
          </button>
        </div>
        {tab === "Investigation" && (
          <div className="investigation-grid">
            <section className="panel network-panel">
              <div className="panel-heading">
                <div>
                  <GitBranch size={17} />
                  <h2>Transaction network</h2>
                  <span className="panel-tag">LIVE CONTEXT</span>
                </div>
                <button
                  className="text-button"
                  onClick={() => {
                    setFilter("account");
                    setTab("Transactions");
                  }}
                >
                  View ledger <ArrowUpRight size={14} />
                </button>
              </div>
              <Graph
                rows={rows}
                account={account}
                onAccount={setAccount}
                selected={selected}
                onTransaction={selectTx}
                path={path}
                threshold={threshold}
              />
              <div className="graph-footer">
                <span>
                  <i className="dot mint" /> Click an account to inspect · click
                  a transfer to review
                </span>
                <span>UTC / same-currency paths</span>
              </div>
            </section>
            <aside className="panel evidence-panel">
              <div className="panel-heading">
                <div>
                  <Search size={16} />
                  <h2>Entity inspector</h2>
                </div>
                <span className="panel-tag">ACCOUNT</span>
              </div>
              <div className="entity-heading">
                <div className="entity-icon">
                  <Box size={22} />
                </div>
                <span className="eyebrow">SELECTED ENTITY</span>
                <h3>{account || "No account selected"}</h3>
                <div className="risk-label">
                  <span
                    className={risk >= threshold ? "amber-text" : "mint-text"}
                  >
                    {(risk * 100).toFixed(risk < 0.001 ? 4 : 2)} / 100
                  </span>
                  <span>Investigation score</span>
                </div>
                <div className="risk-track">
                  <i style={{ width: `${risk * 100}%` }} />
                </div>
                <p className="microcopy">
                  Maximum observed transaction score. Not an account-level
                  probability.
                </p>
              </div>
              <div className="entity-stats">
                <div>
                  <span>INBOUND</span>
                  <b>
                    <ArrowDownRight size={14} />
                    {related.filter((r) => r.target === account).length}
                  </b>
                </div>
                <div>
                  <span>OUTBOUND</span>
                  <b>
                    <ArrowUpRight size={14} />
                    {related.filter((r) => r.source === account).length}
                  </b>
                </div>
                <div>
                  <span>ALERTS</span>
                  <b className="amber-text">
                    {related.filter((r) => r.score >= threshold).length}
                  </b>
                </div>
              </div>
              <div className="evidence-section">
                <span className="tiny-label">OBSERVED INDICATORS</span>
                {[...new Set(related.flatMap((r) => r.reasons))]
                  .slice(0, 3)
                  .map((reason) => (
                    <div className="indicator" key={reason}>
                      <span className="indicator-icon">
                        <GitBranch size={14} />
                      </span>
                      <div>
                        {reason}
                        <small>Rule-based evidence · preceding 24 hours</small>
                      </div>
                    </div>
                  ))}
                {!related.some((r) => r.reasons.length) && (
                  <p className="muted">
                    No behavioral indicator in the observed history.
                  </p>
                )}
              </div>
              <div className="inspector-actions">
                <button
                  className="primary"
                  disabled={!related.length || busyPaths}
                  onClick={trace}
                >
                  <GitBranch size={15} />
                  {busyPaths ? "Tracing…" : "Trace money paths"}
                </button>
                <button onClick={exportCase} disabled={!related.length}>
                  <Download size={15} />
                  Export evidence
                </button>
              </div>
            </aside>
          </div>
        )}
        {(pathsRequested || pathError) && tab === "Investigation" && (
          <section className="panel paths-panel">
            <div className="panel-heading">
              <div>
                <GitBranch size={16} />
                <h2>Chronological paths</h2>
                <span className="panel-tag">{paths.length} FOUND</span>
              </div>
              <button
                aria-label="Close paths"
                onClick={() => {
                  setPathsRequested(false);
                  setPath([]);
                  setPathError("");
                }}
              >
                <X size={16} />
              </button>
            </div>
            <p className="microcopy">
              Connected transfers do not prove that the same funds flowed
              through each account. Up to 30 same-currency paths, five hops.
            </p>
            {pathError && <p className="error">{pathError}</p>}
            {paths.length ? (
              <div className="path-list">
                {paths.map((p, i) => (
                  <button
                    key={i}
                    className={
                      path.join() === p.transaction_ids.join()
                        ? "selected-path"
                        : ""
                    }
                    onClick={() => setPath(p.transaction_ids)}
                  >
                    <span className="panel-tag">{p.pattern}</span>
                    {p.accounts.join(" → ")}
                    <span className="muted">
                      {p.transaction_ids.length} hops
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="empty">
                No chronological path of two or more transfers from this account
                yet.
              </p>
            )}
          </section>
        )}
        {(tab === "Investigation" || tab === "Transactions") && (
          <section className="panel ledger">
            <div className="panel-heading">
              <div>
                <Layers size={16} />
                <h2>Transaction activity</h2>
                <span className="count-badge">{displayed.length}</span>
              </div>
              <div className="table-toolbar">
                <div className="segmented">
                  {[
                    ["all", "All activity"],
                    ["alerts", "Alerts"],
                    ["account", "Selected account"],
                  ].map(([key, label]) => (
                    <button
                      key={key}
                      className={filter === key ? "selected" : ""}
                      onClick={() => setFilter(key)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <label className="search-box">
                  <Search size={14} />
                  <input
                    placeholder="Search accounts or ID"
                    aria-label="Search transactions"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </label>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>TRANSACTION / UTC</th>
                    <th>FROM ACCOUNT</th>
                    <th>TO ACCOUNT</th>
                    <th>AMOUNT</th>
                    <th>SCORE</th>
                    <th>STATUS</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {displayed.slice(0, 200).map((r) => (
                    <tr
                      tabIndex={0}
                      key={r.id}
                      className={r.id === selected ? "selected-row" : ""}
                      onClick={() => selectTx(r.id)}
                      onKeyDown={(e) => e.key === "Enter" && selectTx(r.id)}
                    >
                      <td>
                        <span className="mono">{r.id.slice(0, 14)}</span>
                        <small>
                          {new Date(r.timestamp)
                            .toISOString()
                            .replace("T", " ")
                            .replace(".000Z", " UTC")}
                        </small>
                      </td>
                      <td>{r.source}</td>
                      <td>{r.target}</td>
                      <td className="mono">{money(r.amount, r.currency)}</td>
                      <td>
                        <div className="score-cell">
                          <span
                            className={
                              r.score >= threshold ? "amber-text" : "muted"
                            }
                          >
                            {(r.score * 100).toFixed(r.score < 0.001 ? 4 : 2)}
                          </span>
                          <i>
                            <b
                              style={{
                                width: `${r.score * 100}%`,
                                background:
                                  r.score >= threshold ? "#efac56" : "#7b7b7b",
                              }}
                            />
                          </i>
                        </div>
                      </td>
                      <td>
                        <span
                          className={`status-badge ${r.score >= threshold ? "alert" : "clear"}`}
                        >
                          <i className="dot" />
                          {r.score >= threshold ? "Review" : "Below threshold"}
                        </span>
                      </td>
                      <td>
                        <ChevronRight size={14} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!displayed.length && (
                <p className="empty">
                  No observed transactions match this view.
                </p>
              )}
            </div>
            <div className="table-footer">
              <span>
                Showing {Math.min(displayed.length, 200)} of {displayed.length}{" "}
                matching transfers
              </span>
              <span>
                Scores:{" "}
                {scenario.model.mode === "rules"
                  ? "demonstration rules"
                  : "Laya AML"}
              </span>
            </div>
            {tx && (
              <div className="transaction-detail">
                <span className="tiny-label">
                  SELECTED TRANSFER · DATASET RECORD
                </span>
                <strong>{money(tx.amount, tx.currency)}</strong>
                <details>
                  <summary>Inspect normalized transaction record</summary>
                  <pre>
                    {JSON.stringify(
                      {
                        id: tx.id,
                        timestamp: tx.timestamp,
                        source: tx.source,
                        target: tx.target,
                        amount: tx.amount,
                        currency: tx.currency,
                        payment_format: tx.payment_format,
                        label: tx.label,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
                <strong>
                  {tx.id} · {tx.source} → {tx.target}
                </strong>
                <span>
                  {tx.reasons.join(" · ") ||
                    "No rule-based indicator in available history."}
                </span>
                <small>
                  Ground truth:{" "}
                  {tx.label === null
                    ? "unavailable"
                    : tx.label === 1
                      ? "synthetic laundering label"
                      : "synthetic legitimate label"}{" "}
                  · {tx.payment_format} · {new Date(tx.timestamp).toISOString()}
                </small>
              </div>
            )}
          </section>
        )}
        {tab === "Evaluation" && (
          <section className="panel evaluation-panel">
            <div className="panel-heading">
              <div>
                <Activity size={17} />
                <h2>Detection trade-off</h2>
              </div>
              <span className="panel-tag">
                {sid === "demo" ? "DEMO OBSERVATIONS" : "OBSERVED LABELS"}
              </span>
            </div>
            <div className="evaluation-content">
              <div>
                <h3>Recall & precision</h3>
                <p className="muted">
                  Computed only from labeled, currently observed transactions.
                  This is not a held-out model benchmark.
                </p>
                <svg
                  viewBox="0 0 640 260"
                  className="evaluation-chart"
                  role="img"
                  aria-label="Recall and precision across thresholds"
                >
                  {[0, 0.25, 0.5, 0.75, 1].map((v) => (
                    <g key={v}>
                      <line
                        x1="40"
                        y1={220 - v * 190}
                        x2="620"
                        y2={220 - v * 190}
                        stroke="#2f2f2f"
                      />
                      <text
                        x="4"
                        y={224 - v * 190}
                        fill="#8f8f8f"
                        fontSize="12"
                      >
                        {v * 100}%
                      </text>
                    </g>
                  ))}
                  {(["recall", "precision"] as const).map((metric, i) => (
                    <polyline
                      key={metric}
                      points={Array.from({ length: 101 }, (_, n) => {
                        const t =
                          scenario.model.mode === "laya"
                            ? 10 ** (-7 + n * 0.07)
                            : n / 100;
                        const m = evaluate(rows, t)[metric];
                        return m === null
                          ? ""
                          : `${40 + n * 5.8},${220 - m * 190}`;
                      })
                        .filter(Boolean)
                        .join(" ")}
                      fill="none"
                      stroke={i ? "#efac56" : "#69b8ff"}
                      strokeDasharray={i ? "6 4" : undefined}
                      strokeWidth="2.5"
                    />
                  ))}
                  <line
                    x1={
                      40 +
                      (scenario.model.mode === "laya"
                        ? Math.max(
                            0,
                            (Math.log10(Math.max(1e-7, threshold)) + 7) / 7,
                          )
                        : threshold) *
                        580
                    }
                    x2={
                      40 +
                      (scenario.model.mode === "laya"
                        ? Math.max(
                            0,
                            (Math.log10(Math.max(1e-7, threshold)) + 7) / 7,
                          )
                        : threshold) *
                        580
                    }
                    y1="20"
                    y2="220"
                    stroke="#ececec"
                    strokeDasharray="4 4"
                  />
                  <text x="40" y="248" fill="#8f8f8f" fontSize="12">
                    {scenario.model.mode === "laya"
                      ? "1e-7 · log threshold"
                      : "0.0 threshold"}
                  </text>
                  <text x="555" y="248" fill="#8f8f8f" fontSize="12">
                    1.0
                  </text>
                </svg>
                <div className="chart-legend">
                  <span className="mint-text">— Recall</span>
                  <span className="amber-text">— Precision</span>
                </div>
              </div>
              <div>
                <h3>Confusion matrix</h3>
                <div className="confusion">
                  <div>
                    <span>Correctly flagged</span>
                    <b>{stats.count ? stats.tp : "—"}</b>
                    <small>True positives</small>
                  </div>
                  <div>
                    <span>False alerts</span>
                    <b className="amber-text">{stats.count ? stats.fp : "—"}</b>
                    <small>False positives</small>
                  </div>
                  <div>
                    <span>Missed positives</span>
                    <b className="amber-text">{stats.count ? stats.fn : "—"}</b>
                    <small>False negatives</small>
                  </div>
                  <div>
                    <span>Correctly below threshold</span>
                    <b>{stats.count ? stats.tn : "—"}</b>
                    <small>True negatives</small>
                  </div>
                </div>
                {!stats.count && (
                  <p className="muted">
                    Custom scenarios are unlabeled. Their predictions cannot
                    establish precision or recall.
                  </p>
                )}
              </div>
            </div>
          </section>
        )}
        {tab === "Inference monitor" && (
          <InferenceMonitor threshold={threshold} />
        )}
        {tab === "Model & data" && (
          <section className="panel model-panel">
            <div className="panel-heading">
              <div>
                <Database size={17} />
                <h2>Local inference pipeline</h2>
              </div>
              <span className="panel-tag">OFFLINE READY</span>
            </div>
            <div className="model-grid">
              <article>
                <span className="eyebrow">01 / TRAIN</span>
                <h3>Google Colab</h3>
                <p>
                  Run notebooks/train_laya_colab.ipynb with a GPU runtime.
                  Download the officially linked IBM dataset, prepare
                  chronological partitions, fine-tune the Laya decision head,
                  then calibrate.
                </p>
                <span className="panel-tag">SUPERVISED · FROZEN ENCODER</span>
              </article>
              <article>
                <span className="eyebrow">02 / EXPORT</span>
                <h3>Portable model package</h3>
                <p>
                  The export includes weights, encoder configuration, tokenizer,
                  preprocessing version, fitted temperature, threshold and
                  evaluation report.
                </p>
                <span className="panel-tag">NO CLOUD INFERENCE</span>
              </article>
              <article>
                <span className="eyebrow">03 / INVESTIGATE</span>
                <h3>{scenario.model.name}</h3>
                <p>
                  Set AML_MODEL_DIR to your extracted package and restart the
                  API. The server validates the feature version and required
                  offline files before scoring.
                </p>
                <span className="panel-tag">CPU · SINGLE MODEL</span>
              </article>
            </div>
            <div className="model-facts">
              <h3>What the scores mean</h3>
              <p>
                Transaction score:{" "}
                {scenario.model.mode === "rules"
                  ? "deterministic demonstration rules; not a probability."
                  : "the fine-tuned Laya output with the exported domain temperature."}{" "}
                Account risk: maximum observed transaction score. Pattern
                indicators: causal rules and chronological graph traversal, not
                supervised pattern predictions.
              </p>
              <p>
                Original synthetic demo data is bundled. IBM data is obtained
                separately through the links in IBM/AML-Data. No dataset or
                model weights are committed to Git.
              </p>
              <p>
                Machine target: Windows 11 · Intel i5-12450H · 8 GB RAM · CPU
                inference. Open Inference monitor for measured CPU latency and
                live predictions.
              </p>
              {scenario.model.manifest && (
                <pre>{JSON.stringify(scenario.model.manifest, null, 2)}</pre>
              )}
            </div>
          </section>
        )}
        <section className="threshold-panel">
          <div className="threshold-title">
            <SlidersHorizontal size={18} />
            <div>
              <strong>Detection threshold</strong>
              <small>Lower the threshold to surface more activity</small>
            </div>
          </div>
          <span className="threshold-value mono">
            {threshold < 0.001
              ? threshold.toExponential(3)
              : threshold.toFixed(4)}
          </span>
          <div className="slider-group">
            <input
              aria-label="Detection threshold"
              type="range"
              min={scenario.model.mode === "laya" ? -7 : 0}
              max={scenario.model.mode === "laya" ? 0 : 1}
              step={scenario.model.mode === "laya" ? 0.01 : 0.001}
              value={
                scenario.model.mode === "laya"
                  ? Math.log10(Math.max(1e-7, threshold))
                  : threshold
              }
              onChange={(e) =>
                setThreshold(
                  scenario.model.mode === "laya"
                    ? 10 ** +e.target.value
                    : +e.target.value,
                )
              }
            />
            <div>
              <span>Higher recall</span>
              <span>Fewer alerts</span>
            </div>
          </div>
          <input
            className="exact-threshold"
            aria-label="Exact detection threshold"
            type="number"
            min="0"
            max="1"
            step="any"
            value={threshold}
            onChange={(e) => {
              const v = Number(e.target.value);
              if (Number.isFinite(v) && v >= 0 && v <= 1) setThreshold(v);
            }}
          />
          <button
            onClick={() => setThreshold(scenario.model.default_threshold)}
          >
            <Settings2 size={14} />
            Reset default
          </button>
        </section>
        <footer className="page-footer">
          <span>TRACE / AML RESEARCH ENVIRONMENT</span>
          <span>
            Local processing <span className="footer-dot">·</span>{" "}
            {scenario.model.mode === "rules"
              ? "Demo scoring"
              : "Laya inference"}{" "}
            <span className="footer-dot">·</span> UTC
          </span>
        </footer>
      </main>
      {editor && (
        <Editor
          scenario={scenario}
          onClose={() => setEditor(false)}
          onSave={(id) => {
            setEditor(false);
            setSid(id);
            setTab("Investigation");
            setToast("Scenario saved locally");
          }}
        />
      )}
      {toast && (
        <div className="toast">
          <Check size={16} />
          {toast}
        </div>
      )}
    </div>
  );
}
