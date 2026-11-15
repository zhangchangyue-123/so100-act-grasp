#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
check_arm_read.py —— 用 lerobot 的 FeetechMotorsBus 只读一次数据，验证配置是否生效。
不会写任何寄存器、不会上力矩、不会让舵机动作。

用法（必须先激活环境，并 cd 到 genkiarm 目录）：
  python scripts/check_arm_read.py COM5
  python scripts/check_arm_read.py COM6
"""

import sys

import numpy as np

from lerobot.common.robot_devices.motors.feetech import FeetechMotorsBus

NAMES = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM5"
    motors = {name: (i + 1, "sts3215") for i, name in enumerate(NAMES)}

    bus = FeetechMotorsBus(port=port, motors=motors)
    bus.connect()
    try:
        pos = bus.read_with_motor_ids(bus.motor_models, bus.motor_indices, "Present_Position")
        torque = bus.read_with_motor_ids(bus.motor_models, bus.motor_indices, "Torque_Enable")
        print(f"{port}  Present_Position = {np.asarray(pos).tolist()}")
        print(f"{port}  Torque_Enable    = {np.asarray(torque).tolist()}")
        ok = all(isinstance(v, (int, np.integer)) and 0 <= v <= 4095 for v in pos)
        print("结论：", "6 个舵机全部读到有效位置，配置可用。" if ok else "有舵机没读到，检查 ID / 线序。")
        return 0 if ok else 1
    finally:
        bus.disconnect()


if __name__ == "__main__":
    sys.exit(main())
