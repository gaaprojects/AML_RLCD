import { useMemo, useState } from "react";
import { Crosshair, Minus, Plus } from "lucide-react";
import type { Transaction } from "./types";
import { money } from "./logic";

export default function Graph({
  rows,
  account,
  onAccount,
  selected,
  onTransaction,
  path,
  threshold,
}: {
  rows: Transaction[];
  account: string;
  onAccount: (s: string) => void;
  selected: string;
  onTransaction: (s: string) => void;
  path: string[];
  threshold: number;
}) {
  const [zoom, setZoom] = useState(1);
  const layout = useMemo(() => {
    const all = [...new Set(rows.flatMap((r) => [r.source, r.target]))];
    const focus = all.includes(account) ? account : all[0];
    const neighbors = new Set<string>(focus ? [focus] : []);
    // Include the selected path first, then grow the account neighborhood.
    for (const r of rows.filter((r) => path.includes(r.id))) {
      neighbors.add(r.source);
      neighbors.add(r.target);
    }
    for (let hop = 0; hop < 3; hop++) {
      const frontier = new Set(neighbors);
      for (const r of rows) {
        if (frontier.has(r.source) || frontier.has(r.target)) {
          for (const id of [r.source, r.target])
            if (neighbors.size < 24) neighbors.add(id);
        }
      }
    }
    const ids = [...neighbors].slice(0, 24);
    const pos: Record<string, { x: number; y: number }> = {};
    const special: Record<string, [number, number]> = {
      "NORTHSTAR-01": [115, 150],
      "CEDAR-03": [115, 300],
      "ORION-04": [115, 450],
      "HARBOR-02": [330, 300],
      "ATLAS-05": [550, 150],
      "MERIDIAN-06": [550, 300],
      "VALE-07": [550, 450],
      "SUMMIT-08": [770, 300],
    };
    const isHarbor = ids.every((id) => special[id]);
    const peers = ids.filter((id) => id !== focus);
    ids.forEach((id) => {
      const angle =
        (peers.indexOf(id) / Math.max(peers.length, 1)) * Math.PI * 2 -
        Math.PI / 2;
      pos[id] = isHarbor
        ? { x: special[id][0], y: special[id][1] }
        : id === focus
          ? { x: 440, y: 295 }
          : { x: 440 + 300 * Math.cos(angle), y: 295 + 215 * Math.sin(angle) };
    });
    return {
      ids,
      pos,
      edges: rows.filter((r) => pos[r.source] && pos[r.target]),
      hidden: all.length - ids.length,
    };
  }, [rows, account, path]);
  return (
    <div className="graph-canvas">
      <div className="graph-overlay">
        <span className="tiny-label">DIRECTED TRANSACTION NETWORK</span>
        <span>
          {layout.ids.length} accounts · {layout.edges.length} transfers
          {layout.hidden > 0 ? ` · ${layout.hidden} outside view` : ""}
        </span>
      </div>
      <svg
        viewBox="0 0 880 600"
        aria-label="Interactive transaction network"
        role="group"
      >
        <defs>
          <pattern
            id="grid"
            width="24"
            height="24"
            patternUnits="userSpaceOnUse"
          >
            <circle cx="1" cy="1" r="0.8" fill="#2f2f2f" />
          </pattern>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#686868" />
          </marker>
          <marker
            id="hot-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#b8b8b8" />
          </marker>
        </defs>
        <rect width="880" height="600" fill="url(#grid)" />
        <g
          transform={`translate(${440 * (1 - zoom)},${300 * (1 - zoom)}) scale(${zoom})`}
        >
          {layout.edges.map((r, i) => {
            const a = layout.pos[r.source],
              b = layout.pos[r.target];
            const dx = b.x - a.x,
              dy = b.y - a.y,
              dist = Math.hypot(dx, dy) || 1;
            const x1 = a.x + (dx / dist) * 26,
              y1 = a.y + (dy / dist) * 26,
              x2 = b.x - (dx / dist) * 30,
              y2 = b.y - (dy / dist) * 30;
            const highlighted = path.includes(r.id) || r.id === selected;
            const hot = r.score >= threshold;
            const returning = r.target === "NORTHSTAR-01";
            const d = returning
              ? `M ${x1} ${y1} Q 450 0 ${x2} ${y2}`
              : r.source === r.target
                ? `M ${a.x - 15} ${a.y - 20} C ${a.x - 70} ${a.y - 90}, ${a.x + 70} ${a.y - 90}, ${a.x + 15} ${a.y - 20}`
                : `M ${x1} ${y1} L ${x2} ${y2}`;
            return (
              <g
                key={r.id}
                className={`graph-edge ${highlighted ? "highlighted" : ""}`}
                onClick={() => onTransaction(r.id)}
                tabIndex={0}
                role="button"
                aria-label={`Transfer ${r.source} to ${r.target}, ${money(r.amount, r.currency)}`}
                onKeyDown={(e) => e.key === "Enter" && onTransaction(r.id)}
              >
                <path d={d} className="edge-hit" />
                <path
                  d={d}
                  stroke={highlighted ? "#c7c7c7" : hot ? "#939393" : "#505050"}
                  strokeWidth={highlighted ? 2.8 : 1.3}
                  fill="none"
                  markerEnd={`url(#${hot ? "hot-arrow" : "arrow"})`}
                  strokeDasharray={returning ? "5 5" : undefined}
                />
                {(hot || highlighted) && i < 24 && (
                  <text
                    x={returning ? 450 : (a.x + b.x) / 2}
                    y={returning ? 95 : (a.y + b.y) / 2 - 10}
                    className="edge-label"
                  >
                    {money(r.amount, r.currency)}
                  </text>
                )}
              </g>
            );
          })}
          {layout.ids.map((id) => {
            const p = layout.pos[id];
            const risk = Math.max(
              0,
              ...rows
                .filter((r) => r.source === id || r.target === id)
                .map((r) => r.score),
            );
            const active = id === account;
            return (
              <g
                key={id}
                transform={`translate(${p.x},${p.y})`}
                className="graph-node"
                role="button"
                tabIndex={0}
                aria-label={`Inspect account ${id}`}
                onClick={() => onAccount(id)}
                onKeyDown={(e) => e.key === "Enter" && onAccount(id)}
              >
                {active && (
                  <circle
                    r="35"
                    fill="none"
                    stroke="#c0c0c0"
                    strokeOpacity=".25"
                    strokeDasharray="3 4"
                  />
                )}
                <circle
                  r="25"
                  fill={active ? "#323232" : "#202020"}
                  stroke={
                    active
                      ? "#c5c5c5"
                      : risk >= threshold
                        ? "#919191"
                        : "#595959"
                  }
                  strokeWidth={active ? 2 : 1}
                />
                <path
                  d="M -8 -4 L 0 -9 L 8 -4 M -8 -2 H 8 M -6 0 V 7 M 0 0 V 7 M 6 0 V 7 M -9 9 H 9"
                  fill="none"
                  stroke={active ? "#d6d6d6" : "#bdbdbd"}
                  strokeWidth="1.4"
                />
                <text y="47" className="node-label">
                  {id}
                </text>
                <text y="63" className="node-sub">
                  {Math.round(risk * 100)} / 100 evidence score
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      {!rows.length && (
        <div className="graph-empty">Step forward to reveal transactions.</div>
      )}
      <div className="graph-legend">
        <span>
          <i className="dot mint" />
          Selected path
        </span>
        <span>
          <i className="dot amber" />
          Above threshold
        </span>
        <span>
          <i className="dot gray" />
          Other transfer
        </span>
      </div>
      <div className="graph-tools">
        <button
          aria-label="Zoom out"
          onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))}
        >
          <Minus size={15} />
        </button>
        <button aria-label="Reset graph zoom" onClick={() => setZoom(1)}>
          <Crosshair size={15} />
        </button>
        <button
          aria-label="Zoom in"
          onClick={() => setZoom((z) => Math.min(1.8, z + 0.2))}
        >
          <Plus size={15} />
        </button>
      </div>
    </div>
  );
}
