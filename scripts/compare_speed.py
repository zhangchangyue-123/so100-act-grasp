# -*- coding: utf-8 -*-
"""对比演示与回放的动作节奏：接近耗时、全程耗时、最大关节速度。"""
from pathlib import Path

import os
import torch

FPS = 30


def stats(folder: Path, label: str):
    rows = []
    for p in sorted((folder / "episodes").glob("episode_*.pth"), key=lambda x: int(x.stem.split("_")[1])):
        s = torch.load(p, weights_only=False)["observation.state"].float()
        lift = s[:, 1]
        # 接近耗时：从开始到第一次到达最低点
        i_min = int(torch.argmin(lift).item())
        # 回位时刻：最低点之后第一次回到 80° 以上
        i_back = None
        for i in range(i_min, len(lift)):
            if float(lift[i]) > 80:
                i_back = i
                break
        speed = float((s[:, :5].diff(dim=0).abs() * FPS).max())     # 最大关节角速度 deg/s
        rows.append({
            "approach_s": round(i_min / FPS, 1),
            "cycle_s": round(((i_back if i_back else len(lift)) / FPS), 1),
            "total_s": round(len(lift) / FPS, 1),
            "max_speed": round(speed, 0),
            "min_lift": round(float(lift.min()), 1),
        })
    n = len(rows)
    print(f"\n=== {label}（{n} 条）===")
    for k in ("approach_s", "cycle_s", "total_s", "max_speed", "min_lift"):
        vals = [r[k] for r in rows]
        vals.sort()
        print(f"  {k:<11} 中位数 {vals[n//2]:>6}   范围 {vals[0]} ~ {vals[-1]}")


BASE = Path(os.environ.get("LEROBOT_DATA", "data")).resolve() / "pick"
stats(BASE / "so100_test", "训练演示")
stats(BASE / "eval_long20", "当前回放（20 秒那批）")
print("\napproach_s = 从折叠位伸到积木最低点所需秒数")
print("cycle_s    = 伸下去 + 抓 + 抬起回位 的秒数")
print("max_speed  = 前 5 个关节的最大角速度 deg/s")
