"""Check exported checkpoint parity and CPU latency, strictly offline."""
import argparse
import json
import os
from pathlib import Path
from time import perf_counter
from aml.features import QUESTION


def verify(path):
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", USE_TF="0", AML_MODEL_DIR=str(Path(path).resolve()))
    from aml.scoring import Scorer
    scorer=Scorer()
    if scorer.error or not scorer.agent:
        raise RuntimeError(scorer.error or "Checkpoint not loaded")
    fixture=json.loads((Path(path)/"parity.json").read_text())
    times=[]
    for _ in range(4):
        start=perf_counter()
        result=scorer.probability(fixture["state"])
        times.append(perf_counter()-start)
    actual=result
    delta=abs(actual-fixture["expected_probability"])
    if delta>fixture["absolute_tolerance"]:
        raise ValueError(f"Export parity failed: {delta}")
    return {"parity":"passed","absolute_error":delta,"warm_mean_ms":sum(times[1:])/3*1000,"cold_ms":times[0]*1000}


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("path")
    print(json.dumps(verify(p.parse_args().path),indent=2))
