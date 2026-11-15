# -*- coding: utf-8 -*-
"""临时自检：确认组装好的数据集能被 LeRobotDataset 正常加载、能解出图像和动作。"""
import json
import os
from pathlib import Path

import torch

import os
ROOT = Path(os.environ.get("LEROBOT_DATA", "data")).resolve()
os.environ["DATA_DIR"] = str(ROOT)

from lerobot.common.datasets.lerobot_dataset import LeRobotDataset  # noqa: E402

repo_id = "pick/so100_test"
info = json.loads((ROOT / repo_id / "meta_data" / "info.json").read_text(encoding="utf-8"))
print("info.json :", info)

ds = LeRobotDataset(repo_id)
print("frames    :", len(ds))
print("fps       :", ds.fps, "| video:", ds.video)
print("features  :", list(ds.hf_dataset.features.keys()))
print("episodes  :", ds.num_episodes)
print("stats keys:", list(ds.stats.keys()))

sample = ds[0]
for k, v in sample.items():
    if torch.is_tensor(v):
        print(f"  {k:<32} {tuple(v.shape)} {v.dtype}")
    else:
        print(f"  {k:<32} {type(v).__name__} {v}")

# 抽最后几帧确认 delta_timestamps 动作块能取到
last = ds[len(ds) - 1]
print("last item action:", tuple(last["action"].shape) if torch.is_tensor(last.get("action")) else last.get("action"))
print("OK: dataset 可加载")
