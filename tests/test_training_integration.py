"""Optional CPU contract test: tiny random encoder, never an AML benchmark."""
import json
import os
from argparse import Namespace
from pathlib import Path
import pytest


@pytest.mark.ml
def test_train_resume_export_and_offline_parity(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    pytest.importorskip("laya")
    pytest.importorskip("sklearn")
    monkeypatch.setenv("USE_TF", "0")
    from transformers import BertConfig, BertModel, PreTrainedTokenizerFast
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from safetensors.torch import save_file
    from laya.common import DecisionModel
    from aml.features import FEATURE_VERSION, History, model_state
    from aml.demo import demo_scenario
    from aml.train import train
    from aml.verify_model import verify
    import huggingface_hub

    torch.set_num_threads(2)
    base = tmp_path / "tiny-base"
    base.mkdir()
    raw=Tokenizer(WordLevel({"[PAD]":0,"[UNK]":1,"[CLS]":2,"[SEP]":3,"[MASK]":4,"true":5,"false":6},unk_token="[UNK]"))
    raw.pre_tokenizer=Whitespace()
    tokenizer=PreTrainedTokenizerFast(tokenizer_object=raw,unk_token="[UNK]",pad_token="[PAD]",cls_token="[CLS]",sep_token="[SEP]",mask_token="[MASK]")
    tokenizer.save_pretrained(base / "tokenizer")
    config=BertConfig(vocab_size=7,hidden_size=64,num_hidden_layers=1,num_attention_heads=2,intermediate_size=128,max_position_embeddings=512)
    model=DecisionModel(BertModel(config),head_layers=1,n_act=2)
    model.encoder.config.save_pretrained(base / "encoder")
    save_file(model.state_dict(),str(base / "model.safetensors"))
    (base/"rl_agent_config.json").write_text(json.dumps({"encoder":"local-tiny-test","head_layers":1,"act_costs":{"review":1},"max_len":512,"head_max_len":128}))
    monkeypatch.setattr(huggingface_hub,"snapshot_download",lambda *a,**k:str(base))
    data=tmp_path/"prepared"
    data.mkdir()
    h=History()
    rows=[{"id":t.id,"label":t.label,"state":model_state(t,f),"features":f} for t in demo_scenario().transactions for f in [h.observe(t)]]
    for name in ["train","validation","calibration","test"]:
        (data/f"{name}.jsonl").write_text('\n'.join(json.dumps(r) for r in rows))
    (data/"manifest.json").write_text(json.dumps({"feature_version":FEATURE_VERSION,"sha256":"test-fixture-only","rows":len(rows),"boundaries":[],"synthetic_contract_test":True}))
    args=Namespace(seed=42,allow_cpu=True,out=str(tmp_path/"run"),data=str(data),revision="test",train_rows=46,eval_rows=46,batch_size=2,lr=2e-5,resume=False,epochs=2,max_steps=2,target_recall=.9)
    train(args)
    export=Path(args.out)/"export"
    assert json.loads((export/"evaluation.json").read_text())["steps"]==2
    assert verify(export)["parity"]=="passed"
    args.resume=True
    args.max_steps=3
    train(args)
    assert json.loads((export/"evaluation.json").read_text())["steps"]==3
    assert verify(export)["parity"]=="passed"
