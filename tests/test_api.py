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
