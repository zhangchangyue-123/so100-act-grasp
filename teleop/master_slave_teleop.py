#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""主从六轴机械臂遥操作：主端(COM5)实时读取，从端(COM6)同步模仿。
主端 STS-3215-C066 虚拟舵机 / 从端 STS-3215-C001 第二八舵机。"""

import sys
import time
from pathlib import Path

import serial.tools.list_ports

# 飞特 SDK
SDK_DIR = Path(__file__).resolve().parent.parent / "third_party" / "scservo_sdk"
SDK_PARENT = SDK_DIR.parent
if SDK_PARENT.is_dir() and str(SDK_PARENT) not in sys.path:
    sys.path.insert(0, str(SDK_PARENT))

from scservo_sdk import (  # type: ignore
    COMM_SUCCESS,
    GroupSyncRead,
    PortHandler,
    SMS_STS_ACC,
    SMS_STS_PRESENT_POSITION_L,
    sms_sts,
)

# ───────────────────────── 改这里 ─────────────────────────
MASTER_PORT = "COM5"     # 主端串口（用手推动，读角度）
SLAVE_PORT = "COM6"      # 从端串口（STS-3215-C001，模仿跟随）
BAUDRATE = 1_000_000

# 关节映射：列表每一项 -> (主端servo_id, 从端servo_id, 方向系数, 零位补偿)
#   master : 主端读取该舵机的位置
#   slave  : 从端写入该舵机的目标位置
#   scale  : +1 同向跟随 / -1 反向（镜像）跟随
#   offset : 额外位置补偿，用于消除中位误差（单位：位置单位 0~4095）
#   ratio  : 比例系数，用于校准主从舵机的机械误差（默认1.0）
#   校准方法：将主端放到某个已知位置，读取从端实际位置，offset = 主端位置 - 从端位置
JOINTS = [
    {"master": 1, "slave": 1, "scale": 1, "offset": 0, "ratio": 1.0},   # 关节1
    {"master": 2, "slave": 2, "scale": 1, "offset": 0, "ratio": 1.0},   # 关节2
    {"master": 3, "slave": 3, "scale": 1, "offset": 0, "ratio": 1.0},   # 关节3
    {"master": 4, "slave": 4, "scale": 1, "offset": 0, "ratio": 1.0},   # 关节4
    {"master": 5, "slave": 5, "scale": 1, "offset": 0, "ratio": 1.0},   # 关节5
    {"master": 6, "slave": 6, "scale": 1, "offset": 0, "ratio": 1.0},   # 关节6
]

FOLLOW_SPEED = 2047   # 从端运动速度(0~2047)，2047=最快
FOLLOW_ACC = 253      # 从端加速度(0~253)，253=最快响应
DEADBAND = 1          # 死区：主从角度差小于该值时不写，防止抖动
LOWPASS = 0.7         # 低通滤波系数(0~1)，越大响应越快；0=关闭（纯绝对跟随建议0.7~1.0）

POLL_INTERVAL = 0.03  # 刷新周期(秒)，越快跟随越跟手，建议 0.03~0.1
# ───────────────────────── 到此为止 ─────────────────────────

COUNTS_PER_REVOLUTION = 4096
POSITION_DATA_LENGTH = 2
MID = 2048  # 中位（飞特中位校准后的 0 度）


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def pick_port(default: str, hint: str) -> str | None:
    """选择串口。

    优先使用传入的默认串口(default)；若系统里找不到该串口，
    则列出所有可用串口并让用户手动输入编号选择。
    返回选中的串口名，若没有任何串口则返回 None。
    """
    # 枚举系统全部串口，按设备名(不区分大小写)排序，保证显示顺序稳定
    ports = sorted(
        serial.tools.list_ports.comports(), key=lambda p: p.device.lower()
    )
    # 一个串口都没有：无法连接，直接返回空
    if not ports:
        print(f"[{hint}] 未发现任何串口")
        return None
    # 默认串口不在当前系统列表中，说明端口号变了，需要用户手动选择
    if all(p.device != default for p in ports):
        print(f"[{hint}] 未找到 {default}，可用端口：")
        # 逐个打印候选串口及其描述信息，帮助用户辨认
        for i, p in enumerate(ports):
            print(f"  [{i}] {p.device}  {p.description}")
        # 循环等待用户输入，直到输入合法编号为止
        while True:
            raw = input(f"  请输入编号(0~{len(ports)-1})：").strip()
            try:
                idx = int(raw)
            except ValueError:
                print("  请输入数字")
                continue
            # 编号在合法范围内：返回对应的串口名
            if 0 <= idx < len(ports):
                return ports[idx].device
            print("  编号越界")
    # 默认串口存在，直接使用它，无需人工干预
    return default


def set_slave_goal(slave_pkt, sid: int, position: int, speed: int, acc: int) -> bool:
    """写入从端目标位置。ID 已存在用 changeParam，否则 addParam。"""
    position = slave_pkt.scs_toscs(position, 15)
    txpacket = [
        acc,
        slave_pkt.scs_lobyte(position),
        slave_pkt.scs_hibyte(position),
        0,
        0,
        slave_pkt.scs_lobyte(speed),
        slave_pkt.scs_hibyte(speed),
    ]
    if sid in slave_pkt.groupSyncWrite.data_dict:
        return slave_pkt.groupSyncWrite.changeParam(sid, txpacket)
    return slave_pkt.groupSyncWrite.addParam(sid, txpacket)


def open_bus(dev: str, hint: str):
    ph = PortHandler(dev)
    if not ph.openPort():
        print(f"[{hint}] 打开 {dev} 失败")
        return None
    if not ph.setBaudRate(BAUDRATE):
        print(f"[{hint}] 设置波特率失败")
        ph.closePort()
        return None
    return ph


def main() -> None:
    master_port = pick_port(MASTER_PORT, "主端")
    slave_port = pick_port(SLAVE_PORT, "从端")
    if master_port is None or slave_port is None:
        return

    master_ph = open_bus(master_port, "主端")
    if master_ph is None:
        return
    slave_ph = open_bus(slave_port, "从端")
    if slave_ph is None:
        master_ph.closePort()
        return

    master_pkt = sms_sts(master_ph)
    slave_pkt = sms_sts(slave_ph)

    # 主端同步读
    master_reader = GroupSyncRead(
        master_pkt, SMS_STS_PRESENT_POSITION_L, POSITION_DATA_LENGTH
    )
    for j in JOINTS:
        master_reader.addParam(j["master"])

    slave_ids = [j["slave"] for j in JOINTS]
    for sid in slave_ids:
        set_slave_goal(slave_pkt, sid, MID, FOLLOW_SPEED, FOLLOW_ACC)
    slave_pkt.groupSyncWrite.txPacket()

    print(f"主端连接 {master_port} @ {BAUDRATE}")
    print(f"从端连接 {slave_port} @ {BAUDRATE}")
    print(f"跟随关节数: {len(JOINTS)}  DEADBAND:{DEADBAND}  LOWPASS:{LOWPASS}")
    print("移动主端 → 从端同步跟随。按 Ctrl+C 退出。\n")

    # 上一次写出的从端位置（用于低通/去抖）
    last_output = {j["slave"]: MID for j in JOINTS}

    try:
        while True:
            # 1) 读主端当前位置
            master_reader.txRxPacket()
            targets_written = 0
            master_reads = []
            for joint in JOINTS:
                avail, err = master_reader.isAvailable(
                    joint["master"], SMS_STS_PRESENT_POSITION_L, POSITION_DATA_LENGTH
                )
                if not (avail and err == 0):
                    master_reads.append(f"M{j['master']}=--")
                    continue
                raw = master_reader.getData(
                    joint["master"], SMS_STS_PRESENT_POSITION_L, POSITION_DATA_LENGTH
                )
                master_pos = master_pkt.scs_tohost(raw, 15)
                master_reads.append(f"M{j['master']}={master_pos}")

                # 2) 目标位置 = 主端绝对位置 × 比例系数 + 补偿（绝对跟随模式）
                ratio = joint.get("ratio", 1.0)
                if joint["scale"] == 1:
                    target = int(round(master_pos * ratio))
                else:
                    target = COUNTS_PER_REVOLUTION - 1 - int(round(master_pos * ratio))  # 镜像翻转
                target += joint["offset"]
                target = clamp(target, 0, 4095)

                # 3) 低通平滑（抑制主端手抖传到从端）
                if LOWPASS > 0:
                    prev = last_output[joint["slave"]]
                    target = int(round(prev + LOWPASS * (target - prev)))

                # 4) 死区，避免微抖一直写
                if abs(target - last_output[joint["slave"]]) < DEADBAND:
                    continue

                set_slave_goal(
                    slave_pkt, joint["slave"], target, FOLLOW_SPEED, FOLLOW_ACC
                )
                last_output[joint["slave"]] = target
                targets_written += 1

            # 5) 一次性批量写从端
            if targets_written:
                slave_pkt.groupSyncWrite.txPacket()
            else:
                slave_pkt.groupSyncWrite.clearParam()

            # 诊断：实时显示主端读到的位置（覆盖本行）
            diag = " | ".join(master_reads)
            print(f"{diag} \033[K", end="\r")

            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        slave_ph.closePort()
        master_ph.closePort()


if __name__ == "__main__":
    main()