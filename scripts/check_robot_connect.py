# -*- coding: utf-8 -*-
"""临时自检：走一遍 eval 前 robot.connect() 的完整路径（不含任何运动指令）。"""
import numpy as np
import torch
from hydra.utils import instantiate
from omegaconf import OmegaConf

cfg = OmegaConf.load("lerobot/configs/robot/so100.yaml")
robot = instantiate(cfg)

print("connect() ...")
robot.connect()
try:
    print("  arms     :", list(robot.follower_arms), "+", list(robot.leader_arms))
    print("  cameras  :", list(robot.cameras))
    for name, cam in robot.cameras.items():
        frame = cam.async_read()
        print(f"  {name:<8}: {tuple(np.asarray(frame).shape)}")
    pos = robot.follower_arms["main"].read("Present_Position")
    print("  follower Present_Position:", [round(float(x), 1) for x in torch.as_tensor(pos).flatten()])
finally:
    print("断开并关闭 follower 力矩 ...")
    try:
        robot.follower_arms["main"].write("Torque_Enable", 0)
    except Exception as e:
        print("  disable torque failed:", e)
    robot.disconnect()
print("OK: connect 全链路通过")
