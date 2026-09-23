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

    def probability(self, state):
        # The upstream convenience API rounds to four decimals. AML thresholds
        # can be smaller than 0.0001, so use calibrated logits without rounding.
        import torch
        from laya.common import build_sequence, collate_items, QTYPES
        ids, markers = build_sequence(self.agent.tok, state, QUESTION,
                                      self.agent.cfg["max_len"], self.agent.cfg["head_max_len"])
        if len(markers) != 2:
            raise ValueError("Expected two binary decision markers")
        item = {"ids": ids, "markers": markers, "qtype": QTYPES["noul"]}
        batch = collate_items([[item]], self.agent.tok.pad_token_id)
        with torch.inference_mode():
            logits, _ = self.agent.model(**{k: batch[k].to(self.agent.device) for k in
                ("input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype")})
            temperature = self.agent.temperature_by_options.get("noul:2", self.agent.temperature[QTYPES["noul"]])
            return float(torch.softmax(logits[0, :2].float() / temperature, dim=-1)[1])

    def predict(self, tx, features):
        score, reasons = rule_score(tx, features)
        if self.error:
            raise ValueError(f"Model loading failed: {self.error}")
        if self.agent:
            score = self.probability(model_state(tx, features))
        return score, reasons
