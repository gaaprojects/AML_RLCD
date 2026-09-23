import pytest
from fastapi.testclient import TestClient
from aml import api
from aml.scoring import Scorer


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(api,"DB",tmp_path/"test.sqlite")
    monkeypatch.delenv("AML_MODEL_DIR",raising=False)
    monkeypatch.setattr(api,"scorer",Scorer())
    return TestClient(api.app)


def test_demo_is_honest_and_replay_paths_bounded(client):
    data=client.get("/api/scenarios/demo").json()
    assert data["model"]["mode"]=="rules"
    assert len(data["transactions"])==46
    response=client.get("/api/scenarios/demo/paths",params={"account":"NORTHSTAR-01","visible":0})
    assert response.json()["paths"]==[]
    paths=client.get("/api/scenarios/demo/paths",params={"account":"NORTHSTAR-01"}).json()["paths"]
    assert any(p["pattern"]=="Cycle candidate" for p in paths)


def test_custom_scenarios_persist_and_cannot_inject_ground_truth(client):
    source=client.get("/api/scenarios/demo").json()
    response=client.post("/api/scenarios",json={"name":"New scenario","transactions":source["transactions"][:3]})
    assert response.status_code==201
    sid=response.json()["id"]
    loaded=client.get(f"/api/scenarios/{sid}").json()
    assert all(t["label"] is None for t in loaded["transactions"])
    assert any(s["id"]==sid for s in client.get("/api/scenarios").json())


def test_validation_and_missing_scenario(client):
    assert client.post("/api/scenarios",json={"name":"Invalid","transactions":[]}).status_code==422
    assert client.get("/api/scenarios/nonexistent").status_code==404


def test_bad_checkpoint_does_not_silently_fall_back(client,monkeypatch,tmp_path):
    monkeypatch.setenv("AML_MODEL_DIR",str(tmp_path/"missing"))
    monkeypatch.setattr(api,"scorer",Scorer())
    assert client.get("/api/health").json()["status"]=="degraded"
    assert client.get("/api/scenarios/demo").status_code==503


def test_stream_records_actual_calls_and_distinguishes_cache(client):
    import json
    def events(response):
        return [(block.splitlines()[0][7:], json.loads(block.splitlines()[1][6:]))
                for block in response.text.strip().split("\n\n")]
    first = events(client.get("/api/scenarios/demo/stream?fresh=true"))
    assert first[0][0] == "meta"
    rows = [row for kind, payload in first if kind == "rows" for row in payload]
    assert len(rows) == 46
    assert all(row["inference_ms"] >= 0 for row in rows)
    assert first[-1] == ("complete", {"cached": False})
    status = client.get("/api/inference").json()
    assert status["state"] == "complete"
    assert status["processed"] == status["total"] == 46
    assert len(status["recent"]) == 46
    second = events(client.get("/api/scenarios/demo/stream"))
    assert second[-1] == ("complete", {"cached": True})
    after = client.get("/api/inference").json()
    assert after["processed"] == 46
    assert after["cache_hits"] == status["cache_hits"] + 1


def test_default_prefers_ibm_and_stream_errors_are_visible(client, monkeypatch):
    import json
    from aml.demo import demo_scenario
    source = demo_scenario().model_dump(mode="json")
    source["origin"] = "ibm"
    source["name"] = "Imported IBM replay"
    with api.connection() as db:
        db.execute("INSERT INTO scenarios VALUES (?,?)", ("ibm-test", json.dumps(source)))
    assert api.get_scenario("default").name == "Imported IBM replay"
    def broken(*args):
        raise RuntimeError("Prediction failed")
    monkeypatch.setattr(api.scorer, "predict", broken)
    response = client.get("/api/scenarios/default/stream?fresh=true")
    assert 'event: failure' in response.text
    status = client.get("/api/inference").json()
    assert status["state"] == "error"
    assert status["last_error"] == "Prediction failed"


def test_resource_metrics_and_completed_timer(client):
    client.get("/api/scenarios/demo/stream?fresh=true")
    first = client.get("/api/inference").json()
    second = client.get("/api/inference").json()
    assert first["elapsed_seconds"] == second["elapsed_seconds"]
    assert first["elapsed_seconds"] >= 0
    assert first["remaining_seconds"] is None
    assert first["resources"]["rss_mb"] > 0
    assert first["resources"]["logical_cpus"] >= 1
    assert 0 <= first["resources"]["system_ram_percent"] <= 100
