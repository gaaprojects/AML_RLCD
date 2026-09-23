"""Stream IBM CSV into disk-backed chronological partitions and replay data.

Usage: python -m aml.prepare --csv data/HI-Small_Trans.csv --out data/prepared
"""
import argparse
import csv
import hashlib
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import ExitStack
from aml.domain import Transaction
from aml.features import History, model_state, FEATURE_VERSION

REQUIRED = {"Timestamp", "From Bank", "Account", "To Bank", "Account.1", "Amount Paid", "Payment Currency", "Payment Format", "Is Laundering"}


def ibm_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        original = next(reader)
        seen = {}
        headers = []
        for column in original:
            column = column.strip()
            count = seen.get(column, 0)
            headers.append(column if count == 0 else f"{column}.{count}")
            seen[column] = count + 1
        missing = REQUIRED - set(headers)
        if missing:
            raise ValueError(f"IBM CSV missing columns: {sorted(missing)}")
        for index, values in enumerate(reader):
            if len(values) != len(headers):
                raise ValueError(f"Malformed CSV at line {index+2}")
            r = dict(zip(headers, values))
            try:
                yield Transaction(id=f"IBM-{index:09d}", timestamp=datetime.fromisoformat(r["Timestamp"].replace("/", "-")), source=f'{r["From Bank"]}:{r["Account"]}', target=f'{r["To Bank"]}:{r["Account.1"]}', amount=float(r["Amount Paid"]), currency=r["Payment Currency"], payment_format=r["Payment Format"], label=int(r["Is Laundering"]))
            except Exception as exc:
                raise ValueError(f"Invalid IBM row at line {index+2}: {exc}") from exc


def prepare(csv_path, output, max_rows=0):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # A manifest certifies completion; never leave a prior one over partial files.
    (output / "manifest.json").unlink(missing_ok=True)
    print("Importing IBM CSV into the local chronological index…", flush=True)
    db = sqlite3.connect(output / "transactions.sqlite")
    try:
        db.execute("DROP TABLE IF EXISTS transactions")
        db.execute("CREATE TABLE transactions (id TEXT PRIMARY KEY, timestamp TEXT, body TEXT)")
        digest = hashlib.sha256()
        with open(csv_path, "rb") as src:
            for block in iter(lambda: src.read(1024*1024), b""):
                digest.update(block)
        count = 0
        for tx in ibm_rows(csv_path):
            db.execute("INSERT INTO transactions VALUES (?,?,?)", (tx.id, tx.timestamp.isoformat(), tx.model_dump_json()))
            count += 1
            if count % 10000 == 0:
                db.commit()
            if count % 500000 == 0:
                print(f"Imported {count:,} transactions", flush=True)
            if max_rows and count >= max_rows:
                break
        db.commit()
        if count < 40:
            raise ValueError("At least 40 valid rows required for chronological splits")
        db.execute("CREATE INDEX chronological ON transactions(timestamp,id)")
        print(f"Imported {count:,} transactions. Building causal features and chronological partitions…", flush=True)
        boundaries = [db.execute("SELECT timestamp FROM transactions ORDER BY timestamp,id LIMIT 1 OFFSET ?", (int(count * q),)).fetchone()[0] for q in (.6,.75,.85)]
        if len(set(boundaries)) < 3:
            raise ValueError("Insufficient distinct timestamps for chronological splits")
        names = ["train", "validation", "calibration", "test"]
        stats = {name: {"rows":0,"positives":0,"start":None,"end":None} for name in names}
        history = History()
        replay = []
        with ExitStack() as stack:
            handles = {n:stack.enter_context(open(output / f"{n}.jsonl", "w", encoding="utf-8")) for n in names}
            for processed, (body, stamp) in enumerate(db.execute("SELECT body,timestamp FROM transactions ORDER BY timestamp,id"), 1):
                tx = Transaction.model_validate_json(body)
                features = history.observe(tx)
                split = names[sum(stamp >= b for b in boundaries)]
                handles[split].write(json.dumps({"id":tx.id,"timestamp":stamp,"state":model_state(tx,features),"features":features,"label":tx.label}) + "\n")
                s = stats[split]
                s["rows"] += 1
                s["positives"] += tx.label
                s["start"] = s["start"] or stamp
                s["end"] = stamp
                if len(replay) < 2000:
                    replay.append(tx.model_dump(mode="json"))
                if processed % 500000 == 0:
                    print(f"Prepared {processed:,} / {count:,} transactions", flush=True)
        manifest = {"feature_version":FEATURE_VERSION,"source":str(Path(csv_path).name),"sha256":digest.hexdigest(),"rows":count,"row_limit":max_rows,"selection":"file prefix before chronological ordering" if max_rows else "complete file", "splits":stats,"boundaries":boundaries,"license":"CDLA-Sharing-1.0","pattern_labels":"not provided by this transaction CSV; graph indicators only"}
        (output / "manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        (output / "replay.json").write_text(json.dumps({"name":f"IBM / {Path(csv_path).stem}"[:80],"description":"IBM synthetic data · earliest 2,000 selected transactions · labels available", "origin":"ibm", "transactions":replay}),encoding="utf-8")
        return manifest
    finally:
        db.close()


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv",required=True)
    p.add_argument("--out",default="data/prepared")
    p.add_argument("--max-rows",type=int,default=0,help="0 reads all rows; prefix limits are for smoke tests only")
    args=p.parse_args()
    if args.max_rows < 0:
        p.error("max-rows must be nonnegative")
    print(json.dumps(prepare(args.csv,args.out,args.max_rows),indent=2))
