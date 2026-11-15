# -*- coding: utf-8 -*-
"""最小运动测试：只让 shoulder_pan 转 5 度再回位，验证 send_action -> 舵机 是否真的通。"""
import time

import numpy as np
import torch
from hydra.utils import instantiate
from omegaconf import OmegaConf

cfg = OmegaConf.load("lerobot/configs/robot/so100.yaml")
robot = instantiate(cfg)
robot.connect()
try:
    arm = robot.follower_arms["main"]
    pos0 = torch.as_tensor(arm.read("Present_Position"))
    print("起始 (度):", [round(float(x), 1) for x in pos0])
    print("Torque_Enable:", arm.read("Torque_Enable").tolist())

    goal = pos0.clone()
    goal[0] = goal[0] + 5.0          # 只动底座 5 度
    print("下发 goal:", [round(float(x), 1) for x in goal])
    sent = robot.send_action(goal)
    print("send_action 返回:", [round(float(x), 1) for x in sent])

    time.sleep(1.0)
    pos1 = torch.as_tensor(arm.read("Present_Position"))
    print("1 秒后 (度):", [round(float(x), 1) for x in pos1])
    print("实际变化   :", [round(float(pos1[i] - pos0[i]), 1) for i in range(6)])

    print("回位 ...")
    robot.send_action(pos0)
    time.sleep(1.0)
    pos2 = torch.as_tensor(arm.read("Present_Position"))
    print("回位后 (度):", [round(float(x), 1) for x in pos2])
    moved = abs(float(pos1[0] - pos0[0]))
    print("\n结论:", f"底座实际转了 {moved:.1f} 度 -> 下发链路{'正常' if moved > 2 else '有问题'}")
finally:
    try:
        robot.follower_arms["main"].write("Torque_Enable", 0)
    except Exception:
        pass
    robot.disconnect()
