from datetime import datetime, timedelta, timezone
import csv
import json
import pytest
from aml.domain import Transaction, Scenario
from aml.features import History, model_state, rule_score
from aml.analytics import temporal_paths, metrics
from aml.prepare import prepare, ibm_rows
from aml.train import reservoir


def tx(id="1", minute=0, source="A", target="B", amount=100, currency="USD", label=None):
    return Transaction(id=id,timestamp=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=minute),source=source,target=target,amount=amount,currency=currency,label=label)


def test_causal_history_excludes_labels_future_and_simultaneous_events():
    history=History()
    first=tx(label=1)
    f=history.observe(first)
    assert f["source_in_count"]==0
    simultaneous=history.observe(tx("2",source="B",target="C"))
    assert simultaneous["source_in_count"]==0
    later=tx("3",1,"B","C")
    features=history.observe(later)
    assert features["source_in_count"]==1
    assert features["minutes_since_in"]==1
    serialized=json.dumps(model_state(first,f))
    assert "label" not in serialized and '"A"' not in serialized
    assert rule_score(first,f)==rule_score(first.model_copy(update={"label":0}),f)


def test_currency_and_expiry():
    h=History()
    h.observe(tx())
    f=h.observe(tx("2",1,"B","C",currency="EUR"))
    assert f["source_in_value"]==0
    f=h.observe(tx("3",1441,"B","C"))
    assert f["source_in_count"]==0


def test_reject_reverse_time_and_invalid_amount():
    h=History()
    h.observe(tx(minute=2))
    with pytest.raises(ValueError): h.observe(tx("2",minute=1))
    for amount in [0,-1,float("nan"),float("inf")]:
        with pytest.raises(ValueError): tx(amount=amount)


def test_temporal_paths_never_travel_backwards_or_mix_currency():
    rows=[tx().model_dump(mode="json"),tx("2",1,"B","C").model_dump(mode="json"),tx("3",2,"C","A").model_dump(mode="json"),tx("4",0,"B","D").model_dump(mode="json"),tx("5",3,"B","E",currency="EUR").model_dump(mode="json")]
    paths=temporal_paths(rows,"A")
    assert any(p["pattern"]=="Cycle candidate" for p in paths)
    assert all("4" not in p["transaction_ids"] and "5" not in p["transaction_ids"] for p in paths)
    assert all(len(p["transaction_ids"])<=5 for p in paths)


def test_unlabeled_metrics_and_threshold_inclusivity():
    assert metrics([{"score":.9,"label":None}],.5)["recall"] is None
    result=metrics([{"score":.5,"label":1},{"score":.8,"label":0},{"score":.1,"label":1}],.5)
    assert result["tp"]==1 and result["fp"]==1 and result["fn"]==1


def test_duplicate_transaction_id_rejected():
    with pytest.raises(ValueError): Scenario(name="x",transactions=[tx(),tx()])


def test_currency_aliases_match_editor_and_ibm():
    assert tx(currency="US Dollar").currency == tx(currency="usd").currency == "USD"
    assert tx(currency="Euro").currency == "EUR"


def test_optimized_history_matches_brute_force():
    import random
    rng=random.Random(12)
    h=History()
    observed=[]
    for i in range(400):
        value=tx(str(i),i//2*8,rng.choice("ABC"),rng.choice("ABC"),rng.randint(1,1000),rng.choice(["USD","EUR"]))
        f=h.observe(value)
        previous=[t for t in observed if 0 < (value.timestamp-t.timestamp).total_seconds() <= 86400]
        incoming=[t for t in previous if t.target==value.source]
        outgoing=[t for t in previous if t.source==value.source]
        assert f["source_in_count"]==len(incoming)
        assert f["source_out_count"]==len(outgoing)
        assert f["source_peers"]==len({t.target for t in outgoing})
        assert f["source_in_value"]==sum(t.amount for t in incoming if t.currency==value.currency)
        observed.append(value)


def test_prepare_preserves_time_groups_and_duplicate_ibm_headers(tmp_path):
    source=tmp_path/"ibm.csv"
    with source.open("w",newline="") as f:
        w=csv.writer(f)
        w.writerow(["Timestamp","From Bank","Account","To Bank","Account","Amount Paid","Payment Currency","Payment Format","Is Laundering"])
        # Reverse order deliberately: preparation must sort before features/splits.
        for i in reversed(range(100)):
            stamp=(datetime(2026,1,1)+timedelta(minutes=i//2)).isoformat()
            w.writerow([stamp,"1","AA","2","BB",100,"USD","Wire",i%2])
    assert next(ibm_rows(source)).target=="2:BB"
    output=tmp_path/"prepared"
    manifest=prepare(source,output)
    splits=[manifest["splits"][n] for n in ["train","validation","calibration","test"]]
    assert sum(s["rows"] for s in splits)==100
    for a,b in zip(splits,splits[1:]): assert a["end"]<b["start"]
    for row in (output/"test.jsonl").read_text().splitlines():
        data=json.loads(row)
        assert "label" not in data["state"]
    # Repeat runs replace the disk index safely.
    prepare(source,output)


def test_reservoir_requires_both_classes(tmp_path):
    file=tmp_path/"rows.jsonl"
    file.write_text('\n'.join(json.dumps({"label":0}) for _ in range(10)))
    with pytest.raises(ValueError,match="both labels"): reservoir(file,10,42)
