#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""同时读取 6 个飞特舵机的角度（COM5）。"""

import sys
import time
from pathlib import Path

import serial.tools.list_ports

SDK_DIR = Path(__file__).resolve().parent.parent / "third_party" / "scservo_sdk"
SDK_PARENT = SDK_DIR.parent
if SDK_PARENT.is_dir() and str(SDK_PARENT) not in sys.path:
    sys.path.insert(0, str(SDK_PARENT))

from scservo_sdk import (  # type: ignore
    COMM_SUCCESS,
    GroupSyncRead,
    PortHandler,
    SMS_STS_PRESENT_POSITION_L,
    sms_sts,
)

BAUDRATE = 1_000_000

# ↓↓↓ 在这里改成你标定好的六个舵机编号 ↓↓↓
SERVO_IDS = [1, 2, 3, 4, 5, 6]
# ↑↑↑ 在这里改成你标定好的六个舵机编号 ↑↑↑

COUNTS_PER_REVOLUTION = 4096
POSITION_DATA_LENGTH = 2
ZERO_POSITION = 2048
POLL_INTERVAL = 0.2


def position_to_angle(position: int, zero: int = ZERO_POSITION) -> tuple[float, float]:
    absolute = (position % COUNTS_PER_REVOLUTION) * 360.0 / COUNTS_PER_REVOLUTION
    relative = ((position - zero) * 360.0 / COUNTS_PER_REVOLUTION + 180.0) % 360.0 - 180.0
    return absolute, relative


def pick_port() -> str | None:
    ports = sorted(
        serial.tools.list_ports.comports(),
        key=lambda p: p.device.lower(),
    )
    if not ports:
        print("未发现任何串口，请检查 URT-1 是否已连接")
        return None
    print("可用串口：")
    for i, p in enumerate(ports):
        desc = f"  描述: {p.description}" if p.description else ""
        print(f"  [{i}] {p.device}{desc}")
    if len(ports) == 1:
        print(f"\n仅发现一个串口，自动选用 {ports[0].device}")
        return ports[0].device
    while True:
        raw = input(f"\n请输入编号（0~{len(ports) - 1}）: ").strip()
        try:
            idx = int(raw)
        except ValueError:
            print("请输入数字")
            continue
        if 0 <= idx < len(ports):
            return ports[idx].device
        print(f"编号超出范围，请输入 0~{len(ports) - 1}")


def main() -> None:
    port_name = pick_port()
    if port_name is None:
        return

    port_handler = PortHandler(port_name)
    if not port_handler.openPort():
        print(f"无法打开串口 {port_name}")
        return
    if not port_handler.setBaudRate(BAUDRATE):
        print(f"无法设置波特率 {BAUDRATE}")
        port_handler.closePort()
        return

    packet_handler = sms_sts(port_handler)

    sync_reader = GroupSyncRead(
        packet_handler, SMS_STS_PRESENT_POSITION_L, POSITION_DATA_LENGTH
    )
    for servo_id in SERVO_IDS:
        sync_reader.addParam(servo_id)

    header = f"{'ID':>4}  {'原始位置':>8}  {'绝对角度':>10}  {'相对角度':>10}  状态"
    sep = "-" * len(header)

    print(f"已连接 {port_name} @ {BAUDRATE}")
    print(f"监视舵机 ID: {SERVO_IDS}")

    def render() -> None:
        lines = ["", sep, header, sep]
        for servo_id in SERVO_IDS:
            available, error = sync_reader.isAvailable(
                servo_id, SMS_STS_PRESENT_POSITION_L, POSITION_DATA_LENGTH
            )
            if available and error == 0:
                raw = sync_reader.getData(
                    servo_id, SMS_STS_PRESENT_POSITION_L, POSITION_DATA_LENGTH
                )
                position = packet_handler.scs_tohost(raw, 15)
                absolute, relative = position_to_angle(position)
                lines.append(
                    f"{servo_id:>4}  {position:>8}  {absolute:>9.2f}°  "
                    f"{relative:>+9.2f}°  正常"
                )
            else:
                lines.append(
                    f"{servo_id:>4}  {'--':>8}  {'--':>10}  {'--':>10}  "
                    f"无响应(err=0x{error:02X})"
                )
        print("\n".join(lines))

    render()
    print("\n按 Ctrl+C 退出\n")

    try:
        while True:
            sync_reader.txRxPacket()
            print("\x1b[7A\x1b[2J\x1b[H", end="")
            render()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        port_handler.closePort()


if __name__ == "__main__":
    main()