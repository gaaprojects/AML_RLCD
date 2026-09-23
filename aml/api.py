import json
import os
import sqlite3
from pathlib import Path
from threading import Lock
from collections import OrderedDict
from contextlib import contextmanager
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from time import perf_counter, time
from collections import deque
import psutil
process = psutil.Process()
resource_lock = Lock()
process.cpu_percent(None)
from aml.domain import Scenario
from aml.demo import demo_scenario
from aml.features import History
from aml.analytics import temporal_paths
from aml.scoring import Scorer

ROOT = Path(__file__).resolve().parents[1]
DB = Path(os.environ.get("AML_DB", str(ROOT / "data" / "investigations.sqlite")))
DB.parent.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="AML / Investigation API")
scorer = Scorer()
scoring_lock = Lock()
score_cache = OrderedDict()
monitor_lock = Lock()
monitor = {"state": "idle", "processed": 0, "total": 0, "errors": 0,
           "cache_hits": 0, "total_ms": 0.0, "started": None, "scenario": "", "last_error": None, "ended": None}
recent = deque(maxlen=120)


def record_inference(tx, score, latency):
    with monitor_lock:
        monitor["processed"] += 1
        monitor["total_ms"] += latency
        recent.append({"id": tx.id, "score": score, "label": tx.label,
                       "latency_ms": latency, "at": time()})


@app.get("/api/inference")
def inference_status():
    with monitor_lock:
        result = dict(monitor)
        result["recent"] = list(recent)
    n = result["processed"]
    result["mean_ms"] = result["total_ms"] / n if n else None
    result["throughput"] = n * 1000 / result["total_ms"] if result["total_ms"] else 0
    times = sorted(r["latency_ms"] for r in result["recent"])
    result["p95_ms"] = times[min(len(times)-1, int(len(times)*.95))] if times else None
    result["elapsed_seconds"] = max(0, (result["ended"] or time()) - result["started"]) if result["started"] else 0
    result["remaining_seconds"] = (result["total"]-n)*result["mean_ms"]/1000 if n and result["state"] == "running" else None
    with resource_lock:
        mem = process.memory_info()
        system = psutil.virtual_memory()
        cpu = process.cpu_times()
        result["resources"] = {"process_cpu_percent": process.cpu_percent(None) / (psutil.cpu_count() or 1),
            "rss_mb": mem.rss / 1024**2, "peak_rss_mb": getattr(mem, "peak_wset", mem.rss) / 1024**2,
            "system_ram_percent": system.percent, "available_ram_mb": system.available / 1024**2,
            "cpu_seconds": cpu.user + cpu.system, "threads": process.num_threads(),
            "logical_cpus": psutil.cpu_count(), "device": "CPU"}
    result["model"] = scorer.status()
    return result



@contextmanager
def connection():
    db = sqlite3.connect(DB)
    try:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
            yield db
    finally:
        db.close()


def get_scenario(sid):
    if sid == "default":
        with connection() as db:
            for saved_id, body in db.execute("SELECT id,body FROM scenarios ORDER BY rowid DESC"):
                if json.loads(body).get("origin") == "ibm":
                    return Scenario.model_validate_json(body)
        return demo_scenario()
    if sid == "demo":
        return demo_scenario()
    with connection() as db:
        row = db.execute("SELECT body FROM scenarios WHERE id=?", (sid,)).fetchone()
    if not row:
        raise HTTPException(404, "Scenario not found")
    return Scenario.model_validate_json(row[0])


def score_scenario(scenario):
    history, rows = History(), []
    import hashlib
    key = (scorer, hashlib.sha256(scenario.model_dump_json().encode()).hexdigest())
    with scoring_lock:
        if scorer.error:
            raise ValueError(f"Model loading failed: {scorer.error}")
        if key in score_cache:
            score_cache.move_to_end(key)
            return score_cache[key]
        for tx in sorted(scenario.transactions, key=lambda t: (t.timestamp, t.id)):
            features = history.observe(tx)
            score, reasons = scorer.predict(tx, features)
            rows.append({**tx.model_dump(mode="json"), "score": score, "reasons": reasons, "features": features})
        score_cache[key] = rows
        if len(score_cache) > 3:
            score_cache.popitem(last=False)
    return rows


@app.get("/api/health")
def health():
    return {"status": "degraded" if scorer.error else "ok", "model": scorer.status(), "offline": True}


@app.get("/api/scenarios")
def scenarios():
    with connection() as db:
        saved = [{"id": sid, "name": json.loads(body)["name"]} for sid, body in db.execute("SELECT id,body FROM scenarios ORDER BY rowid DESC")]
    return [{"id": "demo", "name": demo_scenario().name}, *saved]


@app.get("/api/scenarios/{sid}")
def scenario(sid: str):
    value = get_scenario(sid)
    try:
        rows = score_scenario(value)
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"id": sid, "name": value.name, "description": value.description, "origin": value.origin, "transactions": rows, "model": scorer.status()}


@app.get("/api/scenarios/{sid}/stream")
def stream_scenario(sid: str, fresh: bool = False):
    value = get_scenario(sid)
    if scorer.error:
        raise HTTPException(503, scorer.error)

    def event(kind, payload):
        return f"event: {kind}\ndata: {json.dumps(payload)}\n\n"

    def generate():
        import hashlib
        key = (scorer, hashlib.sha256(value.model_dump_json().encode()).hexdigest())
        yield event("meta", {"id": sid, "name": value.name, "description": value.description,
                              "origin": value.origin, "transactions": [], "model": scorer.status(),
                              "total": len(value.transactions)})
        with scoring_lock:
            if not fresh and key in score_cache:
                with monitor_lock:
                    monitor["cache_hits"] += 1
                yield event("rows", score_cache[key])
                yield event("complete", {"cached": True})
                return
            with monitor_lock:
                monitor.update(state="running", processed=0, total=len(value.transactions),
                               total_ms=0.0, started=time(), ended=None, scenario=value.name, last_error=None)
                recent.clear()
            history, rows = History(), []
            try:
                for tx in sorted(value.transactions, key=lambda t: (t.timestamp, t.id)):
                    features = history.observe(tx)
                    start = perf_counter()
                    score, reasons = scorer.predict(tx, features)
                    latency = (perf_counter()-start)*1000
                    record_inference(tx, score, latency)
                    row = {**tx.model_dump(mode="json"), "score": score, "reasons": reasons,
                           "features": features, "inference_ms": latency}
                    rows.append(row)
                    yield event("rows", [row])
                score_cache[key] = rows
                if len(score_cache) > 3:
                    score_cache.popitem(last=False)
                with monitor_lock:
                    monitor["state"] = "complete"
                    monitor["ended"] = time()
                yield event("complete", {"cached": False})
            except GeneratorExit:
                with monitor_lock:
                    monitor["state"] = "cancelled"
                    monitor["ended"] = time()
                raise
            except Exception as exc:
                with monitor_lock:
                    monitor.update(state="error", last_error=str(exc), ended=time())
                    monitor["errors"] += 1
                yield event("failure", {"detail": str(exc)})
            finally:
                with monitor_lock:
                    if monitor["state"] == "running":
                        monitor["state"] = "cancelled"
                        monitor["ended"] = time()

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/scenarios", status_code=201)
def save_scenario(value: Scenario):
    # User-authored scenarios are not ground truth evaluation data.
    for tx in value.transactions:
        tx.label = None
    value.origin = "custom"
    sid = uuid4().hex[:12]
    with connection() as db:
        db.execute("INSERT INTO scenarios VALUES (?,?)", (sid, value.model_dump_json()))
    return {"id": sid, "name": value.name}


@app.get("/api/scenarios/{sid}/paths")
def paths(sid: str, account: str, visible: int = Query(2000, ge=0, le=2000)):
    rows = [t.model_dump(mode="json") for t in sorted(get_scenario(sid).transactions, key=lambda t: (t.timestamp, t.id))][:visible]
    return {"paths": temporal_paths(rows, account), "note": "Chronological, same-currency connections; not proof of fund identity. Limited to 30 paths and 5 hops."}


if (ROOT / "dist").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "dist", html=True), name="frontend")
