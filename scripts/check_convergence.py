# -*- coding: utf-8 -*-
"""离线对比各 checkpoint 在训练集上的动作预测误差，判断 40k 是否还在收敛（不动机械臂）。"""
import os
from pathlib import Path

import torch
from torch.utils.data import DataLoader

os.environ.setdefault("DATA_DIR", str(Path(os.environ.get("LEROBOT_DATA", "data")).resolve()))

from lerobot.common.datasets.lerobot_dataset import LeRobotDataset  # noqa: E402
from lerobot.common.policies.act.modeling_act import ACTPolicy  # noqa: E402

CKPT_ROOT = Path(os.environ.get("ACT_CHECKPOINTS", "outputs/train/act_so100_50eps/checkpoints"))
FPS = 30
CHUNK = 100

ds = LeRobotDataset(
    "pick/so100_test",
    delta_timestamps={"action": [i / FPS for i in range(CHUNK)]},
)
print("dataset frames:", len(ds))

# 固定抽 64 个样本（跨整段均匀取，避开开头结束的边界 pad）
idxs = list(range(200, len(ds) - 200, max((len(ds) - 400) // 64, 1)))[:64]
subset = torch.utils.data.Subset(ds, idxs)
loader = DataLoader(subset, batch_size=16, shuffle=False, num_workers=0)

batches = []
for b in loader:
    batches.append({k: v for k, v in b.items() if isinstance(v, torch.Tensor)})

print(f"{'checkpoint':>10} {'l1_loss':>10} {'kl_loss':>10}")
last = None
for name in ("010000", "020000", "030000", "040000"):
    path = CKPT_ROOT / name / "pretrained_model"
    if not path.exists():
        print(f"{name:>10}  (missing)")
        continue
    policy = ACTPolicy.from_pretrained(str(path))
    policy.eval().to("cuda")
    l1_sum, kl_sum, n = 0.0, 0.0, 0
    with torch.no_grad():
        for b in batches:
            b = {k: v.to("cuda") for k, v in b.items()}
            out = policy(b)
            l1_sum += float(out["l1_loss"]) * len(b["action"])
            kl_sum += float(out.get("kl_loss", torch.zeros(1))) * len(b["action"])
            n += len(b["action"])
    print(f"{name:>10} {l1_sum / n:>10.4f} {kl_sum / n:>10.4f}")
    last = (name, l1_sum / n)
    del policy
    torch.cuda.empty_cache()

print("\nl1_loss 是归一化动作空间里的平均绝对误差，越小越好；如果 040000 仍明显低于 030000，说明还没收敛。")
