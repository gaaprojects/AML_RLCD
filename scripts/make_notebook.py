"""Generate a clean, executable Colab notebook from readable cells."""
import json
from pathlib import Path

cells=[]
def markdown(text): cells.append({"cell_type":"markdown","metadata":{},"source":text.splitlines(keepends=True)})
def code(text): cells.append({"cell_type":"code","execution_count":None,"metadata":{},"outputs":[],"source":text.splitlines(keepends=True)})
markdown("""# TRACE · Train Laya for AML
Supervised fine-tuning on IBM's synthetic transactions, followed by domain calibration and an offline export.

**Runtime → Change runtime type → T4 GPU.** Colab Free GPU availability is not guaranteed. The default 600 steps are a feasibility pilot, not a claim of useful AML accuracy. Increase training after inspecting validation results. No API keys are needed for Laya; Kaggle may ask you to authenticate for dataset access.

Source: https://github.com/IBM/AML-Data (data: CDLA-Sharing-1.0). Model: https://huggingface.co/convaiinnovations/laya (Apache-2.0). Raw data and weights stay outside Git.
""")
code("""from pathlib import Path
import os, subprocess, sys
REPO = 'https://github.com/gaaprojects/AML_RLCD.git'
WORK = Path('/content/AML_RLCD')
if not WORK.exists():
    subprocess.run(['git', 'clone', REPO, str(WORK)], check=True)
os.chdir(WORK)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-e', '.[ml,data]'], check=True)
os.environ['USE_TF'] = '0'
import torch
assert torch.cuda.is_available(), 'Enable a GPU runtime before training.'
print(torch.cuda.get_device_name(0))
print('Project revision:', subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip())
""")
markdown("""## 1 · Persistent checkpoints
Mount Google Drive so a Colab disconnection does not lose the training state. Drive access is requested interactively by Colab.
""")
code("""from google.colab import drive
drive.mount('/content/drive')
RUN = Path('/content/drive/MyDrive/AML_RLCD/laya-pilot')
RUN.mkdir(parents=True, exist_ok=True)
""")
markdown("""## 2 · Obtain IBM data
The GitHub repository links to Kaggle; it does not contain the CSV. Download only the HI-Small transaction file. If Kaggle requires authentication, use its notebook authentication prompt; never paste credentials into a committed cell.
""")
code("""from aml.download_data import download
csv_path = download('data/raw', 'HI-Small_Trans.csv')
print(csv_path)
""")
markdown("""## 3 · Prepare chronological partitions
SQLite sorts on disk. Account history is limited to preceding 24 hours; simultaneous events are excluded. Raw account IDs, labels and future transfers never enter the model input. Training/validation/calibration/test use 60/15/10/15 chronological boundaries; equal timestamps stay together. Preparation reads the entire file by default and can take several minutes.
""")
code("""from aml.prepare import prepare
manifest = prepare(csv_path, 'data/prepared')
print(manifest['splits'])
assert all(s['positives'] > 0 and s['positives'] < s['rows'] for s in manifest['splits'].values()), 'Both classes are needed in every partition.'
""")
markdown("""## 4 · Train the Laya decision head
The encoder and unused act/escalate head are frozen. Natural-prevalence uniform samples are used without oversampling. Checkpoints save every 50 optimizer steps. Re-running with `--resume` restores model head, optimizer, scaler, RNG and position; increase MAX_STEPS to continue the pilot. Evaluation samples must contain both labels; increase EVAL_ROWS if needed. Default evaluation can take longer than training.
""")
code("""MAX_STEPS = 600
TRAIN_ROWS = 12000
EVAL_ROWS = 10000
command = [sys.executable, '-m', 'aml.train', '--data', 'data/prepared', '--out', str(RUN),
           '--max-steps', str(MAX_STEPS), '--train-rows', str(TRAIN_ROWS), '--eval-rows', str(EVAL_ROWS),
           '--batch-size', '2', '--target-recall', '0.90', '--resume']
subprocess.run(command, check=True)
""")
markdown("""## 5 · Inspect held-out results
Temperature is fit on calibration only. A threshold targeting 90% validation recall is selected before test evaluation. Test recall is not guaranteed to meet that target. Compare Laya against the logistic-regression baseline and examine false alerts, prevalence, PR-AUC and reliability bins. Graph pattern indicators are not supervised pattern classifications.
""")
code("""import json
report = json.loads((RUN / 'export/evaluation.json').read_text())
print(json.dumps(report, indent=2))
""")
markdown("""## 6 · Verify offline export and download
A fresh CPU load must reproduce a stored training-side prediction within tolerance. This validates serialization/preprocessing parity, not detection quality. Unload notebook GPU caches before this separate process if necessary.
""")
code("""subprocess.run([sys.executable, '-m', 'aml.verify_model', str(RUN / 'export')], check=True)
import shutil
archive = shutil.make_archive('/content/laya-aml', 'zip', RUN / 'export')
from google.colab import files
files.download(archive)
files.download(str(WORK / 'data/prepared/replay.json'))
""")
markdown("""## 7 · Run locally on Windows
Extract `laya-aml.zip` into `models/laya-aml`. Install the optional model dependencies using `scripts/setup.ps1 -WithModel` (internet required once). Run `python -m aml.verify_model models/laya-aml`, then `scripts/start.ps1 -ModelDir models/laya-aml`.

To load the labeled IBM replay, copy `replay.json` to `data/replay.json`, run `python -m aml.import_replay data/replay.json`, and refresh the app. The browser scenario editor creates unlabeled custom data only. No browser CSV upload is included.

Keep `manifest.json` and `evaluation.json` with your model. RLCD, supervised pattern labels, and independently validated account-level probabilities remain separate future experiments.
""")
out=Path('notebooks/train_laya_colab.ipynb')
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps({"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},"language_info":{"name":"python","version":"3.11"},"accelerator":"GPU","colab":{"name":"TRACE_Laya_AML.ipynb","provenance":[]}},"nbformat":4,"nbformat_minor":5},indent=2),encoding='utf-8')
