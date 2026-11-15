# -*- coding: utf-8 -*-
"""测单次推理延迟（batch=1），这是端侧部署的基线数字。不连机械臂。"""
import time
from pathlib import Path

import numpy as np
import torch

from lerobot.common.policies.act.modeling_act import ACTPolicy

PATH = "outputs/train/act_so100_50eps/checkpoints/last/pretrained_model"
policy = ACTPolicy.from_pretrained(PATH).eval().to("cuda")

obs = {
    "observation.images.laptop": torch.rand(1, 3, 480, 640, device="cuda"),
    "observation.images.phone": torch.rand(1, 3, 480, 640, device="cuda"),
    "observation.state": torch.zeros(1, 6, device="cuda"),
}

# 预热
with torch.inference_mode():
    for _ in range(10):
        policy.select_action(obs)
torch.cuda.synchronize()

lat = []
with torch.inference_mode():
    for _ in range(100):
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        policy.select_action(obs)
        torch.cuda.synchronize()
        lat.append((time.perf_counter() - t0) * 1000)

lat = np.array(lat)
print(f"单次推理延迟 (RTX 4060 Laptop, batch=1, 2×480×640):")
print(f"  mean {lat.mean():.1f} ms | p50 {np.percentile(lat,50):.1f} ms | "
      f"p95 {np.percentile(lat,95):.1f} ms | max {lat.max():.1f} ms")
print(f"  30 Hz 的预算是 33.3 ms/步 -> {'跟得上' if np.percentile(lat,95) < 33.3 else '跟不上'}")
print(f"  峰值显存 {torch.cuda.max_memory_allocated()/1024**2:.0f} MiB")
n = sum(p.numel() for p in policy.parameters())
print(f"  参数量 {n/1e6:.1f} M, fp32 权重约 {n*4/1024**2:.0f} MiB, 量化到 INT8 约 {n/1024**2:.0f} MiB")
