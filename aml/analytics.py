from collections import defaultdict


def metrics(rows, threshold):
    labeled = [r for r in rows if r.get("label") is not None]
    tp = sum(r["score"] >= threshold and r["label"] == 1 for r in labeled)
    fp = sum(r["score"] >= threshold and r["label"] == 0 for r in labeled)
    fn = sum(r["score"] < threshold and r["label"] == 1 for r in labeled)
    tn = len(labeled) - tp - fp - fn
    return {"labeled": len(labeled), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "brier": sum((r["score"] - r["label"]) ** 2 for r in labeled) / len(labeled) if labeled else None}


def temporal_paths(rows, start, max_hops=5, limit=30):
    edges = defaultdict(list)
    for r in sorted(rows, key=lambda r: (r["timestamp"], r["id"])):
        edges[r["source"]].append(r)
    result = []
    budget = [5000]
    def visit(account, after, path, visited):
        if len(result) >= limit or budget[0] <= 0:
            return
        for r in edges.get(account, []):
            budget[0] -= 1
            if budget[0] <= 0 or len(result) >= limit:
                break
            if after and r["timestamp"] <= after:
                continue
            if path and r["currency"] != path[0]["currency"]:
                continue
            next_path = path + [r]
            cycle = r["target"] == start
            if len(next_path) >= 2:
                result.append({"transaction_ids": [x["id"] for x in next_path], "accounts": [start] + [x["target"] for x in next_path], "pattern": "Cycle candidate" if cycle else "Chain candidate"})
            if not cycle and r["target"] not in visited and len(next_path) < max_hops:
                visit(r["target"], r["timestamp"], next_path, visited | {r["target"]})
    visit(start, None, [], {start})
    return result
