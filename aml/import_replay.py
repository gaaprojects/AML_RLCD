"""Install a prepared labeled IBM replay into the local scenario database."""
import argparse
import json
import sqlite3
from pathlib import Path
from uuid import uuid4
from aml.domain import Scenario


def install(path, database):
    scenario=Scenario.model_validate_json(Path(path).read_text(encoding="utf-8"))
    database=Path(database)
    database.parent.mkdir(parents=True,exist_ok=True)
    sid=uuid4().hex[:12]
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        db.execute("INSERT INTO scenarios VALUES (?,?)",(sid,scenario.model_dump_json()))
    return sid


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("path")
    p.add_argument("--database",default="data/investigations.sqlite")
    a=p.parse_args()
    print(install(a.path,a.database))
