# TRACE · AML investigation simulator

A local, dark investigation workspace for tracing synthetic financial transactions. Train a Laya decision head on IBM AML data in Google Colab, export it, and run inference on a Windows CPU.

## Run the application

Requirements: Windows, Python 3.11+ and Node.js 22+. Initial setup requires internet. The built application uses no external fonts, CDNs, APIs or cloud inference.

```powershell
.\scripts\setup.ps1
.\scripts\start.ps1
```

Open **http://127.0.0.1:8000**. A project-local virtual environment is used. If Python is not on PATH, pass `-Python "C:\path\to\python.exe"` to setup. PowerShell may require an execution policy appropriate to your environment; alternatively run the commands below manually.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
npm ci
npm run build
.\.venv\Scripts\python.exe -m uvicorn aml.api:app --host 127.0.0.1 --port 8000
```

The original synthetic **Harbor** scenario works immediately with clearly labeled deterministic rules. These are **not trained Laya predictions, calibrated probabilities, or IBM benchmark results**. If an explicitly configured checkpoint fails to load, scoring fails visibly instead of silently substituting rules.

## Investigation workflow

- Play, pause, reset or step through a scenario. Only observed transactions appear in graphs and metrics.
- Select an account to inspect incoming/outgoing activity and rule-based evidence.
- Trace chronological, same-currency chains and cycles. Paths are limited to five hops and 30 results; graph views to 24 connected accounts. Connected transfers do not prove identity of funds.
- Adjust the threshold to explore alert volume, false alerts and recall. Metrics exclude unlabeled transactions. UI metrics describe the visible replay, not an independent benchmark.
- Create accounts implicitly by adding transfers in the on-screen editor. Chain, cycle and fan-in templates are editable. Custom scenarios are saved in local SQLite and always unlabeled.
- Export the selected account's evidence as JSON. Transaction tables show at most 200 matching rows; scenarios contain at most 2,000 transactions for responsive investigation.

Account risk is the maximum observed incident transaction score. It is not a calibrated account-level probability. Fan-in/fan-out indicators and chain/cycle paths are heuristic candidates, not supervised pattern predictions. The current training pipeline uses binary laundering labels. IBM also distributes `HI-Small_Patterns.txt`: the downloaded file contains 370 attempts across eight pattern types and 3,209 transaction lines. Supervised pattern classification remains pending an audited join to transaction rows and a separate evaluation; missing sidecar entries must not be interpreted as legitimate transactions.

### Full dataset verification

On 23 September 2026, complete-file preparation successfully processed 5,078,345 transactions from `HI-Small_Trans.csv` (SHA-256 `b19d39f515523373f991b689c07e11e7b0b95c17a2c27a87d91584ae16c5b040`). The chronological partitions contain:

| Partition   | Transactions | Laundering labels |
| ----------- | -----------: | ----------------: |
| Train       |    3,046,861 |             2,297 |
| Validation  |      761,731 |               777 |
| Calibration |      507,650 |               542 |
| Test        |      762,103 |             1,561 |

The first 2,000 transactions are installed in the local investigation database as **IBM / HI-Small_Trans**. Dataset preparation is verified; an AML-trained Laya checkpoint and its predictive performance have not yet been produced. The notebook's small default training run is a feasibility pilot, not a benchmark.

## Train in Colab Free

[Open the training notebook in Google Colab](https://colab.research.google.com/github/gaaprojects/AML_RLCD/blob/main/notebooks/train_laya_colab.ipynb)

Open [`notebooks/train_laya_colab.ipynb`](notebooks/train_laya_colab.ipynb) in Colab and select a GPU runtime. The notebook includes data download, preparation, Drive checkpoints, supervised training, a tabular baseline, calibration, evaluation and package download.

1. Install the project with `.[ml,data]`. Laya's code is pinned to an inspected upstream commit. The resolved Hugging Face checkpoint revision is recorded in the export.
2. Obtain **HI-Small_Trans.csv** from the Kaggle source linked by [IBM/AML-Data](https://github.com/IBM/AML-Data). GitHub itself contains documentation, not the CSV. Kaggle may require authentication.
3. Sort on disk and create 60/15/10/15 chronological train/validation/calibration/test partitions. Equal timestamps stay in one split. Features use only strictly earlier transactions in the preceding 24 hours. Amount aggregates never mix currencies. Bank IDs qualify account identifiers.
4. Fine-tune the Laya decision head with the encoder frozen. Defaults are a **600-step feasibility pilot**, batch size 2, 12,000 natural-prevalence training examples and 10,000 per evaluation partition. These are uniform reservoir samples, not the full dataset or balanced samples. Increase coverage if a sample lacks either label. Low positive counts limit conclusions; inspect the reported counts.
5. Choose the best head by validation log loss. Fit temperature on calibration data and select the largest threshold reaching target validation recall (90% default). Report test PR-AUC, log loss, Brier score, reliability bins, precision/recall and false alerts. The target is not a guarantee of test recall.
6. Compare against a logistic-regression baseline using the same numeric features and partitions. Export tokenizer, encoder config, weights, feature version, temperature, threshold, provenance and evaluation report.
7. Validate export parity before downloading. RLCD is a future experiment; this implementation uses supervised cross entropy.

GPU training and useful AML performance must be validated by actually running the notebook. Colab Free availability, memory and session duration vary. Default evaluation can take longer than the pilot training. A model is not supplied with this repository.

### Resume training

Drive stores `resume.pt` every 50 steps and at epoch boundaries. The notebook passes `--resume`; rerun with a larger `MAX_STEPS` to continue. Keep seed, dataset, sampling sizes, batch size and learning rate unchanged. Checkpoint signatures reject incompatible resumes. Files contain this application's own training state; do not substitute untrusted checkpoint files.

### Local model installation

```powershell
.\scripts\setup.ps1 -WithModel
# Extract the Colab ZIP into models/laya-aml before these commands:
.\.venv\Scripts\python.exe -m aml.verify_model models/laya-aml
.\scripts\start.ps1 -ModelDir models/laya-aml
```

Offline flags are set before loading. The runtime requires local tokenizer and encoder configurations. Verification compares an exported prediction within a 0.005 probability tolerance and measures warm CPU latency. On an 8 GB computer, close memory-heavy applications during model loading; actual latency and peak memory are not yet established for a trained checkpoint.

### Import IBM replay data

The notebook also downloads `replay.json`, containing the earliest 2,000 prepared transactions. Copy it to `data/replay.json`, then:

```powershell
.\.venv\Scripts\python.exe -m aml.import_replay data/replay.json
```

Refresh the app and select the imported scenario. This CLI preserves verified dataset labels; the browser editor strips labels from user-created scenarios. Replay starts at the beginning of the selected data so its past-only features match preparation.

### Data preparation without Colab

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[data]"
.\.venv\Scripts\python.exe -m aml.download_data
.\.venv\Scripts\python.exe -m aml.prepare --csv data/raw/HI-Small_Trans.csv --out data/prepared
.\.venv\Scripts\python.exe -m aml.import_replay data/prepared/replay.json
```

Raw and processed data, model weights, local databases and training artifacts are ignored by Git. `--max-rows` in preparation reads a file prefix before sorting and is for smoke tests only; the manifest records this restriction. Complete-file preparation is the default.

## Development and checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm test
npm run build
# Separate terminals during development:
.\.venv\Scripts\python.exe -m uvicorn aml.api:app --host 127.0.0.1 --port 8000
npm run dev
```

Tests cover causal features, currency boundaries, chronological splits, path order, label exclusion, invalid data, scenario persistence, threshold metrics and checkpoint failure behavior. The frontend is bundled and served by FastAPI in normal local operation. There is no authentication: bind only to loopback, as the supplied launcher does.

## Layout

| Directory    | Purpose                                                                   |
| ------------ | ------------------------------------------------------------------------- |
| `src/`       | React/TypeScript investigation frontend                                   |
| `aml/`       | API, shared features, rules, data preparation, model runtime and training |
| `notebooks/` | Colab training workflow                                                   |
| `scripts/`   | Windows launch/setup and notebook generator                               |
| `tests/`     | Backend and pipeline checks                                               |

## Sources and licensing

- [Laya](https://huggingface.co/convaiinnovations/laya): Apache-2.0, [upstream implementation](https://github.com/NandhaKishorM/laya).
- [IBM AML-Data](https://github.com/IBM/AML-Data): repository Apache-2.0; **actual data CDLA-Sharing-1.0**, per IBM's documentation. Preserve dataset notices when distributing data.
- The bundled Harbor scenario was authored for this application and is not redistributed IBM data.

This is a research simulator. Synthetic-data performance does not establish performance on real financial activity.

## Installed checkpoint and live monitoring

The downloaded Colab export is installed locally in `models/laya-aml`; model weights remain excluded from Git. `scripts/start.ps1` now loads this directory by default. Pass `-ModelDir ""` explicitly to run demonstration rules instead.

The workspace selects the newest imported IBM replay by default. Predictions stream progressively while **Inference monitor** reports model latency, rolling p95, model throughput, progress, errors and the latest 120 calls. Its table shows the latest 20 predictions. Replay controls become available when scoring completes. Replaying cached results does not execute model inference; **Run inference again** forces fresh model calls. Telemetry and the three-scenario prediction cache last for the server session.

Laya inference preserves full probability precision before applying thresholds. The slider uses a logarithmic scale from 1e-7 to 1 for Laya; the adjacent numeric field permits exact values, including zero. Blue marks selected paths and recall, amber marks alerts and precision, and dashed lines distinguish the latter. Confusion-matrix outcomes also have text labels and separate accents.

The installed pilot's exported test report contains 10,000 transactions and 24 positives: recall 83.33%, precision 0.45%, and 4,390 false alerts. Its 2,000-row imported replay is from the beginning of the training period; replay metrics are not held-out test performance. IBM transactions are synthetic, not a live bank feed.
