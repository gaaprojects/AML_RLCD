"""Supervised Laya decision-head fine-tuning; designed for one Colab GPU.

Run after aml.prepare. No RLCD training or supervised pattern labels are claimed.
"""
import argparse
import json
import os
import random
import platform
from importlib.metadata import version
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
from aml.features import FEATURE_VERSION, NUMERIC_FEATURES, QUESTION


def reservoir(path, limit, seed):
    rng = random.Random(seed)
    rows = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            row = json.loads(line)
            if len(rows) < limit:
                rows.append(row)
            else:
                j = rng.randint(0, i)
                if j < limit:
                    rows[j] = row
    if not rows or {r["label"] for r in rows} != {0, 1}:
        raise ValueError(f"{path}: both labels are required. Increase sample size or dataset coverage.")
    return rows


def train(args):
    import numpy as np
    import torch
    import torch.nn.functional as F
    from huggingface_hub import snapshot_download
    from safetensors.torch import save_file, load_file
    from sklearn.metrics import average_precision_score, precision_recall_curve, brier_score_loss, log_loss
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    import laya
    from laya.common import QTYPES, build_sequence, collate_items

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if not torch.cuda.is_available() and not args.allow_cpu:
        raise RuntimeError("Select a Colab GPU runtime. CPU training requires explicit --allow-cpu.")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    source = Path(args.data)
    data_manifest = json.loads((source / "manifest.json").read_text())
    if data_manifest["feature_version"] != FEATURE_VERSION:
        raise ValueError("Rebuild prepared data with the current preprocessing version")
    datasets = {name: reservoir(source / f"{name}.jsonl", args.train_rows if name == "train" else args.eval_rows, args.seed + i) for i, name in enumerate(["train", "validation", "calibration", "test"])}
    for name, rows in datasets.items():
        print(name, len(rows), "rows; positives:", sum(r["label"] for r in rows), flush=True)

    base = snapshot_download("convaiinnovations/laya", revision=args.revision, allow_patterns=["rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*"])
    agent = laya.load(base, device=device)
    agent.cfg["max_len"] = 512
    agent.cfg["head_max_len"] = 128
    model = agent.model
    for p in model.encoder.parameters():
        p.requires_grad_(False)
    # Act/escalate is not a supervised AML output; freeze and do not expose it.
    for p in model.act_head.parameters():
        p.requires_grad_(False)
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.lr, weight_decay=0.01)
    scaler = torch.amp.GradScaler("cuda", enabled=device == "cuda")

    def encode(row):
        ids, markers = build_sequence(agent.tok, row["state"], QUESTION, agent.cfg["max_len"], agent.cfg["head_max_len"])
        if len(markers) != 2:
            raise ValueError("Binary decision requires two option markers")
        # Detect state truncation instead of silently training on incomplete history.
        empty, _ = build_sequence(agent.tok, "", QUESTION, agent.cfg["max_len"], agent.cfg["head_max_len"])
        state_tokens = agent.tok(json.dumps(row["state"], ensure_ascii=False), add_special_tokens=False)["input_ids"]
        if len(empty) + len(state_tokens) > agent.cfg["max_len"]:
            raise ValueError("State exceeds token budget; revise the shared feature schema")
        return {"ids":ids,"markers":markers,"qtype":QTYPES["noul"],"label":row["label"]}

    encoded = {name:[encode(r) for r in rows] for name, rows in datasets.items()}
    keys = ("input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype")
    def forward(items):
        batch = collate_items([items], agent.tok.pad_token_id)
        with torch.autocast(device_type=device, dtype=torch.float16, enabled=device == "cuda"):
            logits, _ = model(**{k:batch[k].to(device) for k in keys})
        return logits[:, :2].float(), batch["label"].to(device)

    @torch.no_grad()
    def infer(name):
        model.eval()
        values = []
        for i in range(0, len(encoded[name]), args.batch_size):
            logits, _ = forward(encoded[name][i:i+args.batch_size])
            values.append(logits.cpu())
        return torch.cat(values)

    checkpoint = out / "resume.pt"
    signature = {"data_sha256":data_manifest["sha256"],"prepared_rows":data_manifest["rows"],"boundaries":data_manifest["boundaries"],"base_revision":Path(base).name,"seed":args.seed,"train_rows":args.train_rows,"eval_rows":args.eval_rows,"batch_size":args.batch_size,"lr":args.lr,"feature_version":FEATURE_VERSION}
    start_epoch, start_index, step, best = 0, 0, 0, float("inf")
    if args.resume and checkpoint.exists():
        state = torch.load(checkpoint, map_location=device, weights_only=True)
        if state["signature"] != signature:
            raise ValueError("Resume settings or dataset differ from the saved run")
        model.load_state_dict(state["head"], strict=False)
        optimizer.load_state_dict(state["optimizer"])
        scaler.load_state_dict(state["scaler"])
        start_epoch, start_index, step, best = state["epoch"], state["index"], state["step"], state["best"]
        torch.set_rng_state(state["rng"].cpu())
        if device == "cuda" and state["cuda_rng"] is not None:
            torch.cuda.set_rng_state(state["cuda_rng"].cpu())

    def save_checkpoint(epoch, index):
        temporary = out / "resume.tmp"
        torch.save({"signature":signature,"head":{k:v.detach().cpu() for k,v in model.state_dict().items() if not k.startswith("encoder.")},"optimizer":optimizer.state_dict(),"scaler":scaler.state_dict(),"epoch":epoch,"index":index,"step":step,"best":best,"rng":torch.get_rng_state(),"cuda_rng":torch.cuda.get_rng_state() if device == "cuda" else None}, temporary)
        temporary.replace(checkpoint)

    stop = False
    for epoch in range(start_epoch, args.epochs):
        order = list(range(len(encoded["train"])))
        random.Random(args.seed + epoch).shuffle(order)
        index = start_index if epoch == start_epoch else 0
        for index in range(start_index if epoch == start_epoch else 0, len(order), args.batch_size):
            if step >= args.max_steps:
                stop = True
                break
            model.train()
            model.encoder.eval()  # Frozen encoder dropout must not drift.
            optimizer.zero_grad(set_to_none=True)
            logits, labels = forward([encoded["train"][j] for j in order[index:index+args.batch_size]])
            loss = F.cross_entropy(logits, labels)  # Natural prevalence; no label balancing.
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(trainable, 1.0)
            scaler.step(optimizer)
            scaler.update()
            step += 1
            if step % 50 == 0:
                save_checkpoint(epoch, index+args.batch_size)
                print(f"step={step} loss={loss.item():.5f}", flush=True)
        validation_logits = infer("validation")
        validation_labels = torch.tensor([r["label"] for r in datasets["validation"]])
        validation_loss = F.cross_entropy(validation_logits, validation_labels).item()
        if validation_loss < best:
            best = validation_loss
            save_file({k:v.detach().cpu().contiguous() for k,v in model.state_dict().items() if not k.startswith("encoder.")}, str(out / "best-head.safetensors"))
        next_index = index if stop else 0
        save_checkpoint(epoch if stop else epoch+1, next_index)
        print(f"epoch={epoch+1} validation_log_loss={validation_loss:.5f}", flush=True)
        if stop:
            break
    best_path = out / "best-head.safetensors"
    if not best_path.exists():
        raise RuntimeError("No completed training checkpoint")
    model.load_state_dict(load_file(str(best_path), device=device), strict=False)

    cal_logits = infer("calibration")
    cal_labels = torch.tensor([r["label"] for r in datasets["calibration"]])
    temperatures = torch.linspace(0.5, 5.0, 181)
    temperature = float(min(temperatures, key=lambda t:F.cross_entropy(cal_logits/t, cal_labels).item()))
    val_probs = (infer("validation") / temperature).softmax(-1)[:,1].numpy()
    val_y = np.array([r["label"] for r in datasets["validation"]])
    precision, recall, thresholds = precision_recall_curve(val_y, val_probs)
    candidates = np.where(recall[:-1] >= args.target_recall)[0]
    threshold = float(thresholds[candidates[-1]]) if len(candidates) else 0.0
    test_probs = (infer("test") / temperature).softmax(-1)[:,1].numpy()
    test_y = np.array([r["label"] for r in datasets["test"]])

    def report(y, probabilities, cutoff):
        pred = probabilities >= cutoff
        tp, fp, fn = int(((y==1)&pred).sum()), int(((y==0)&pred).sum()), int(((y==1)&~pred).sum())
        bins=[]
        for i in range(10):
            sel=(probabilities>=i/10)&(probabilities<((i+1)/10) if i<9 else probabilities<=1)
            bins.append({"count":int(sel.sum()),"predicted":float(probabilities[sel].mean()) if sel.any() else None,"observed":float(y[sel].mean()) if sel.any() else None})
        return {"rows":len(y),"positives":int(y.sum()),"average_precision":float(average_precision_score(y,probabilities)),"brier":float(brier_score_loss(y,probabilities)),"log_loss":float(log_loss(y,probabilities,labels=[0,1])),"threshold":cutoff,"precision":tp/(tp+fp) if tp+fp else None,"recall":tp/(tp+fn) if tp+fn else None,"false_alerts":fp,"missed":fn,"reliability_bins":bins,"ece":sum(b["count"]/len(y)*abs(b["predicted"]-b["observed"]) for b in bins if b["count"])}

    def matrix(name):
        return [[r["features"][k] for k in NUMERIC_FEATURES] for r in datasets[name]]
    baseline = make_pipeline(StandardScaler(),LogisticRegression(max_iter=1000,random_state=args.seed))
    baseline.fit(matrix("train"),[r["label"] for r in datasets["train"]])
    bp,br,bt = precision_recall_curve(val_y,baseline.predict_proba(matrix("validation"))[:,1])
    qualifying = np.where(br[:-1]>=args.target_recall)[0]
    baseline_threshold = float(bt[qualifying[-1]]) if len(qualifying) else 0.0
    results = {"laya_test":report(test_y,test_probs,threshold),"baseline_test":report(test_y,baseline.predict_proba(matrix("test"))[:,1],baseline_threshold),"validation":report(val_y,val_probs,threshold),"sampling":"Uniform reservoir per chronological split; original prevalence retained in expectation", "samples":{k:{"rows":len(v),"positives":sum(r["label"] for r in v)} for k,v in datasets.items()},"target_recall":args.target_recall,"steps":step}
    export = out / "export"
    export.mkdir(exist_ok=True)
    agent.tok.save_pretrained(export / "tokenizer")
    model.encoder.config.save_pretrained(export / "encoder")
    agent.cfg["temperature"] = [1.0,1.0,temperature]
    agent.cfg["temperature_by_options"] = {"noul:2":temperature}
    (export / "rl_agent_config.json").write_text(json.dumps(agent.cfg,indent=2))
    # fp16 serialization reduces package size; the runtime reconstructs fp32 CPU parameters.
    save_file({k:(v.detach().cpu().half() if v.is_floating_point() else v.detach().cpu()).contiguous() for k,v in model.state_dict().items()},str(export / "model.safetensors"))
    manifest={**signature,"model":"Laya AML supervised decision head","threshold":threshold,"temperature":temperature,"training":"supervised cross entropy; frozen encoder","data":data_manifest,"evaluation":results,"pattern_classifier":False,"runtime_versions":{name:version(name) for name in ("torch","transformers","laya","numpy","scikit-learn","safetensors","huggingface_hub")},"python":platform.python_version()}
    (export / "manifest.json").write_text(json.dumps(manifest,indent=2))
    (export / "evaluation.json").write_text(json.dumps(results,indent=2))
    # Verify the same sample against the exported checkpoint in a fresh load.
    example = datasets["test"][0]["state"]
    expected = float(test_probs[0])
    (export / "parity.json").write_text(json.dumps({"state":example,"expected_probability":expected,"absolute_tolerance":0.005}))
    print(json.dumps(results,indent=2),flush=True)
    print(f"Export complete: {export}. Run python -m aml.verify_model {export} before deployment.",flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data",default="data/prepared")
    p.add_argument("--out",default="artifacts/laya-aml")
    p.add_argument("--revision",default="main")
    p.add_argument("--train-rows",type=int,default=12000)
    p.add_argument("--eval-rows",type=int,default=10000)
    p.add_argument("--batch-size",type=int,default=2)
    p.add_argument("--epochs",type=int,default=2)
    p.add_argument("--max-steps",type=int,default=600)
    p.add_argument("--lr",type=float,default=2e-5)
    p.add_argument("--target-recall",type=float,default=.90)
    p.add_argument("--seed",type=int,default=42)
    p.add_argument("--resume",action="store_true")
    p.add_argument("--allow-cpu",action="store_true")
    a=p.parse_args()
    if min(a.train_rows,a.eval_rows,a.batch_size,a.epochs,a.max_steps)<1 or not 0<a.target_recall<=1:
        p.error("Positive sample, batch, epoch and step counts and recall in (0,1] required")
    train(a)


if __name__=="__main__":
    main()
