#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
consolidate_dataset.py —— 把已录好的 episodes + PNG 帧组装成可训练的 LeRobotDataset

背景（就是你遇到的那个报错）：
    record 结束后，lerobot 的 populate_dataset.create_lerobot_dataset() 会调用 ffmpeg，
    把 videos/<key>_episode_xxxxxx/frame_%06d.png 编码成 mp4；随后才写 train/*.arrow
    和 meta_data/（info.json、stats.safetensors、episode_data_index.safetensors）。
    如果 ffmpeg 不存在，这一步抛 FileNotFoundError，于是：
        episodes/*.pth     ✅ 已经落盘（state/action/timestamp 都在）
        videos/*/frame_*.png ✅ 已经落盘（每帧一张 PNG）
        videos/*.mp4        ❌ 没生成
        train/、meta_data/   ❌ 没生成
    也就是说：数据没丢，只是缺了"组装"这一步。本脚本把这一步补上。

用法（必须 cd 到 genkiarm 目录、激活 jszn01 环境）：
    python scripts/consolidate_dataset.py
    python scripts/consolidate_dataset.py --skip-stats
    python scripts/consolidate_dataset.py --num-workers 4

说明：
  * 每成功编码一个 episode 的 mp4，就会删掉对应的 PNG 帧目录（和原流程一致，能省 10 GB）；
  * episodes/*.pth 永远不会被改；
  * 已存在的 mp4 会被跳过，所以中途失败可以直接重跑。
"""

import argparse
import sys
from pathlib import Path

from lerobot.common.datasets.compute_stats import compute_stats
from lerobot.common.datasets.populate_dataset import (
    from_dataset_to_lerobot_dataset,
    init_dataset,
    save_lerobot_dataset_on_disk,
)


def main():
    ap = argparse.ArgumentParser(description="把已录好的 episodes + PNG 帧组装成可训练的 LeRobotDataset")
    ap.add_argument("--repo-id", default="pick/so100_test", help="数据集标识，默认 pick/so100_test")
    ap.add_argument("--root", default="data", help="数据根目录，默认 data")
    ap.add_argument("--fps", type=int, default=30, help="录制时的帧率，默认 30")
    ap.add_argument("--skip-stats", action="store_true", help="跳过统计量计算（快，但训练归一化会缺参数）")
    ap.add_argument("--num-workers", type=int, default=0, help="统计阶段的 dataloader 进程数，默认 0（Windows 最稳）")
    args = ap.parse_args()

    local_dir = Path(args.root) / args.repo_id
    if not local_dir.exists():
        print(f"找不到数据集目录：{local_dir.resolve()}")
        return 1

    dataset = init_dataset(
        repo_id=args.repo_id,
        root=args.root,
        force_override=False,
        fps=args.fps,
        video=True,
        write_images=False,
        num_image_writer_processes=0,
        num_image_writer_threads=0,
    )

    num_episodes = dataset["num_episodes"]
    print(f"数据集目录 : {local_dir.resolve()}")
    print(f"发现 episode: {num_episodes}")
    if num_episodes == 0:
        print("没有任何 episode，退出。")
        return 1

    import lerobot.common.datasets.video_utils as vu

    print(f"ffmpeg      : {vu.get_ffmpeg_exe()}")
    print("开始组装（PNG -> mp4）...")

    lerobot_dataset = from_dataset_to_lerobot_dataset(dataset, play_sounds=False)

    if args.skip_stats:
        print("跳过统计量计算（--skip-stats）")
        lerobot_dataset.stats = {}
    else:
        print("计算数据集统计量（这一步会解码全部视频，最慢）...")
        lerobot_dataset.stats = compute_stats(lerobot_dataset, num_workers=args.num_workers)

    print("写入 train/ 与 meta_data/ ...")
    save_lerobot_dataset_on_disk(lerobot_dataset)

    print("\n完成 ✅")
    print(f"  {local_dir / 'videos'}      mp4 视频")
    print(f"  {local_dir / 'train'}       arrow 数据")
    print(f"  {local_dir / 'meta_data'}   info / stats / episode_data_index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
