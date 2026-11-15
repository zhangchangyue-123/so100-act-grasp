# -*- coding: utf-8 -*-
"""准确版：40k / 10k 模型的 loss 与"度"单位动作误差。"""
import os
from pathlib import Path

import torch
from torch.utils.data import DataLoader

os.environ.setdefault("DATA_DIR", str(Path(os.environ.get("LEROBOT_DATA", "data")).resolve()))

from lerobot.common.datasets.lerobot_dataset import LeRobotDataset  # noqa: E402
from lerobot.common.policies.act.modeling_act import ACTPolicy  # noqa: E402

CKPT_ROOT = Path(os.environ.get("ACT_CHECKPOINTS", "outputs/train/act_so100_50eps/checkpoints"))
JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
N_SAMPLES = 64

ds = LeRobotDataset("pick/so100_test", delta_timestamps={"action": [i / 30 for i in range(100)]})
idxs = list(range(200, len(ds) - 200, max((len(ds) - 400) // N_SAMPLES, 1)))[:N_SAMPLES]
loader = DataLoader(torch.utils.data.Subset(ds, idxs), batch_size=16, shuffle=False, num_workers=0)
batches = [{k: v for k, v in b.items() if isinstance(v, torch.Tensor)} for b in loader]

for name in ("010000", "040000"):
    path = CKPT_ROOT / name / "pretrained_model"
    policy = ACTPolicy.from_pretrained(str(path)).eval().to("cuda")
    l1_sum, kld_sum, n = 0.0, 0.0, 0
    chunk_err = torch.zeros(6, device="cuda")
    first_err = torch.zeros(6, device="cuda")
    total = 0
    with torch.no_grad():
        for b in batches:
            b = {k: v.to("cuda") for k, v in b.items()}
            out = policy(b)
            l1_sum += float(out["l1_loss"]) * len(b["action"])
            kld_sum += float(out["kld_loss"]) * len(b["action"])
            n += len(b["action"])

            nb = policy.normalize_inputs(b)
            if policy.expected_image_keys:
                nb = dict(nb)
                nb["observation.images"] = torch.stack([nb[k] for k in policy.expected_image_keys], dim=-4)
            nb = policy.normalize_targets(nb)
            actions_hat, _ = policy.model(nb)
            pred = policy.unnormalize_outputs({"action": actions_hat})["action"]
            err = (pred - b["action"]).abs()                       # (B, 100, 6) 单位：度
            chunk_err += err.sum(dim=(0, 1))                       # 每个关节在 100 步上的总和
            first_err += err[:, 0].sum(0)
            total += err.shape[0]

    print(f"\n=== {name} ===")
    print(f"l1_loss  = {l1_sum / n:.4f}   (归一化动作空间的平均绝对误差)")
    print(f"kld_loss = {kld_sum / n:.4f}")
    print(f"动作块误差（100 步平均，度）:  " + "  ".join(
        f"{j}={float(chunk_err[i]) / (total * 100):.2f}" for i, j in enumerate(JOINTS)))
    print(f"  六个关节平均              :  {float(chunk_err.sum()) / (total * 100 * 6):.2f}°")
    print(f"只有第 1 步（实际下发的那一步）:  " + "  ".join(
        f"{j}={float(first_err[i]) / total:.2f}" for i, j in enumerate(JOINTS)))
    print(f"  六个关节平均              :  {float(first_err.sum()) / (total * 6):.2f}°")
    del policy
    torch.cuda.empty_cache()
