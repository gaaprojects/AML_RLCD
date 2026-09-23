import json
import os
from pathlib import Path
from aml.features import FEATURE_VERSION, QUESTION, model_state, rule_score


class Scorer:
    def __init__(self):
        self.agent = None
        self.error = None
        self.manifest = None
        model_dir = os.environ.get("AML_MODEL_DIR")
        if model_dir:
            try:
                root = Path(model_dir).resolve(strict=True)
                self.manifest = json.loads((root / "manifest.json").read_text())
                if self.manifest["feature_version"] != FEATURE_VERSION:
                    raise ValueError("Incompatible preprocessing version")
                for name in ("model.safetensors", "rl_agent_config.json", "tokenizer/tokenizer.json", "encoder/config.json"):
                    if not (root / name).is_file():
                        raise ValueError(f"Incomplete offline package: {name}")
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                os.environ["USE_TF"] = "0"
                import torch
                torch.set_num_threads(4)
                import laya
                self.agent = laya.load(str(root), device="cpu")
            except Exception as exc:
                self.error = str(exc)

    def status(self):
        return {"mode": "laya" if self.agent else "rules", "name": "Laya / AML fine-tuned" if self.agent else "Demonstration rules", "error": self.error, "manifest": self.manifest, "default_threshold": self.manifest.get("threshold", 0.35) if self.agent else 0.35}

    def predict(self, tx, features):
        score, reasons = rule_score(tx, features)
        if self.error:
            raise ValueError(f"Model loading failed: {self.error}")
        if self.agent:
            q = {"risk": {"type": QUESTION["t"], "instructions": QUESTION["ins"]}}
            score = self.agent.predict(model_state(tx, features), q)["answers"]["risk"]["noul"]
        return score, reasons
