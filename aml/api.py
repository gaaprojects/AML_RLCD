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
