"""Obtain IBM's published dataset through the Kaggle source linked by IBM/AML-Data."""
import argparse
from pathlib import Path
import shutil
import time

DATASET="ealtman2019/ibm-transactions-for-anti-money-laundering-aml"


def download(output, filename="HI-Small_Trans.csv"):
    import kagglehub
    # One file, not the entire multi-gigabyte dataset. Authentication may be
    # requested by Kaggle; never store access tokens in repository files.
    from requests.exceptions import ConnectionError, Timeout, ChunkedEncodingError
    for attempt in range(3):
        try:
            cached=Path(kagglehub.dataset_download(DATASET,path=filename))
            break
        except (ConnectionError, Timeout, ChunkedEncodingError):
            if attempt == 2:
                raise
            print(f"Download interrupted; retrying ({attempt+2}/3)…", flush=True)
            time.sleep(2)
    source=cached / filename if cached.is_dir() else cached
    destination=Path(output) / filename
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,destination)
    return destination


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",default="data/raw")
    p.add_argument("--file",default="HI-Small_Trans.csv",choices=["HI-Small_Trans.csv","LI-Small_Trans.csv"])
    a=p.parse_args()
    print(download(a.out,a.file))
