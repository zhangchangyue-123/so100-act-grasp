#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_cameras.py —— 一次性看清"哪几个 index 是真摄像头、分辨率多少、画面是什么"

用法（在你自己的 PowerShell / jszn01 环境里跑，不要在我这边跑，我这边没有摄像头权限）：
    python scripts/probe_cameras.py

它会：
  1. 对 index 0~7 依次用默认后端打开，读一帧，打印分辨率；
  2. 把每个能出图的 index 存成 cam_<index>.jpg；
  3. 最后提示你去 camera_probe/ 看图片，确认哪个是"笔记本"、哪个是"手机"。
"""

import os
import sys

import cv2

SAVE_DIR = os.environ.get("CAMERA_PROBE_DIR", "camera_probe")
MAX_INDEX = 8


def main():
    os.makedirs(SAVE_DIR, exist_ok=True)
    print(f"OpenCV {cv2.__version__}  截图目录: {SAVE_DIR}")
    print("-" * 70)

    found = []
    for idx in range(MAX_INDEX):
        cap = cv2.VideoCapture(idx)
        opened = cap.isOpened()
        shape = None
        if opened:
            ok, frame = cap.read()
            if ok and frame is not None:
                shape = frame.shape
                path = os.path.join(SAVE_DIR, f"cam_{idx}.jpg")
                cv2.imwrite(path, frame)
            cap.release()
        print(f"index {idx}: opened={opened:<5} frame={'None' if shape is None else f'{shape[1]}x{shape[0]}'}")
        if shape is not None:
            found.append(idx)

    print("-" * 70)
    if found:
        print("可用的 index:", found)
        print(f"打开 {SAVE_DIR} 看 cam_*.jpg，把对应的 index 填回 so100.yaml 的 camera_index")
    else:
        print("没有可用摄像头。常见原因：")
        print("  1) 手机当摄像头（Iriun / DroidCam / Camo）的 App 没启动，或 USB 线没插；")
        print("  2) 摄像头被别的程序占用（微信 / 钉钉 / OBS / 之前崩溃没退出的 python.exe）；")
        print("  3) Windows 隐私设置：设置 → 隐私和安全性 → 相机 → 允许桌面应用访问相机。")
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
