# -*- coding: utf-8 -*-
"""汇总任意一个评估数据集：动作形态表 + 俯视末帧接触表（看积木是否进盒）。"""
import argparse
import os
from pathlib import Path

import cv2
import torch
from PIL import Image, ImageDraw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--cols", type=int, default=5)
    args = ap.parse_args()

    folder = Path(args.folder)
    out = Path(os.environ.get("EVAL_ANALYSIS_DIR", "eval_analysis")).resolve()
    out.mkdir(exist_ok=True)

    print(f"=== {folder.name} ===")
    print(f"{'#':>3} {'帧':>4} {'秒':>5} {'大臂最低':>8} {'结束角':>7} {'夹爪行程':>7}  形态")
    rows = []
    for p in sorted((folder / "episodes").glob("episode_*.pth"), key=lambda x: int(x.stem.split("_")[1])):
        idx = int(p.stem.split("_")[1])
        s = torch.load(p, weights_only=False)["observation.state"].float()
        min_lift = float(s[:, 1].min())
        end_lift = float(s[-1, 1])
        grip = float(s[:, 5].max() - s[:, 5].min())
        pat = "没动" if min_lift > -30 else ("只下探没回位" if end_lift < 50 else "下探+回位")
        rows.append((idx, len(s), min_lift, end_lift, grip, pat))
        print(f"{idx:>3} {len(s):>4} {len(s)/30:>5.1f} {min_lift:>8.1f} {end_lift:>7.1f} {grip:>7.1f}  {pat}")

    n = len(rows)
    print()
    for pat in ("下探+回位", "只下探没回位", "没动"):
        k = sum(1 for r in rows if r[5] == pat)
        print(f"{pat:<12} {k:>2}/{n}")
    print(f"平均时长 {sum(r[1] for r in rows)/n/30:.1f}s，平均大臂最低 {sum(r[2] for r in rows)/n:.1f}°")

    cols, tw, th = args.cols, 320, 240
    nrows = (n + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, nrows * th), (25, 25, 25))
    draw = ImageDraw.Draw(sheet)
    for i, (idx, *_rest) in enumerate(rows):
        mp4 = folder / "videos" / f"observation.images.phone_episode_{idx:06d}.mp4"
        frame = None
        if mp4.exists():
            cap = cv2.VideoCapture(str(mp4))
            cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(cnt - 2, 0))
            ok, f = cap.read()
            cap.release()
            frame = f if ok else None
        cx, cy = (i % cols) * tw, (i // cols) * th
        if frame is not None:
            sheet.paste(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).resize((tw, th)), (cx, cy))
        draw.rectangle([cx, cy, cx + tw - 1, cy + th - 1], outline=(255, 255, 255))
        draw.rectangle([cx, cy, cx + 34, cy + 18], fill=(0, 0, 0))
        draw.text((cx + 4, cy + 3), f"#{idx}", fill=(255, 255, 0))
    path = out / f"{folder.name}_phone_last.jpg"
    sheet.save(path, quality=90)
    print("末帧接触表:", path)


if __name__ == "__main__":
    main()
