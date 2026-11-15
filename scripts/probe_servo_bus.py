#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
probe_servo_bus.py —— 舵机总线探测器（只发 PING / 读寄存器，不会动电机、不会上力矩）

用途：当 lerobot 的 teleoperate 刷屏 "Failed to write/read data ... for Motor 'N'"，
      说明那条总线上的帧根本没有回应。本脚本用来判断是哪一种情况：
        1) 线没插好 / 舵机没供电        -> 所有协议、所有波特率都没回应
        2) 波特率不对                  -> 只有某个波特率有回应
        3) 协议选错了（驱动用错了）      -> 只有 FF FF(SCS/STS/Genki M1) 或只有 AA AA(GBot) 有回应

三种探测方式：
  A. 0xFF 0xFF 帧：SCS / SMS-STS / 飞特 STS3215 / Genki M1（lerobot 的 feetech.py、genki.py 都用这个）
  B. 0xAA 0xAA 帧：GBot（lerobot 的 gbot.py 用这个，寄存器表和 A 完全不同）
  C. 官方 scservo_sdk（site-packages 里已安装）作为交叉验证，排除手写解析出错的可能

用法：
  python scripts/probe_servo_bus.py
  python scripts/probe_servo_bus.py --ports COM5 COM6
  python scripts/probe_servo_bus.py --selftest
"""

import argparse
import sys
import time

import serial
from serial.tools import list_ports

# ---------------------------------------------------------------- 0xFF 帧

def ff_checksum(core):
    """SCS/STS 协议校验和：~(ID+LEN+INST/ERR+params) & 0xFF"""
    return (~sum(core)) & 0xFF


def ff_packet(motor_id, instruction, params=()):
    core = [motor_id, len(params) + 2, instruction] + list(params)
    return bytes([0xFF, 0xFF] + core + [ff_checksum(core)])


def ff_parse(buf):
    """
    解析 0xFF 0xFF 响应帧，返回 [(id, error, params_bytes), ...]

    帧格式：FF FF ID LEN ERR P1..Pn CHK，总长 LEN+4，其中 LEN = n+2
    所以 ERR+params 共 LEN-1 字节，CHK 在 LEN+3 位置。
    """
    out = []
    i = 0
    n = len(buf)
    while i + 5 <= n:
        if buf[i] != 0xFF or buf[i + 1] != 0xFF:
            i += 1
            continue
        mid, length = buf[i + 2], buf[i + 3]
        if length < 2 or i + length + 4 > n:
            break
        body = buf[i + 4: i + 3 + length]          # ERR + params，共 length-1 字节
        if len(body) != length - 1:
            break
        chk = buf[i + 3 + length]
        if ff_checksum([mid, length] + list(body)) != chk:
            i += 1
            continue
        out.append((mid, body[0], bytes(body[1:])))
        i += length + 4
    return out


# ---------------------------------------------------------------- 0xAA 帧（GBot）

GBOT_HEADER = 0xAA
GBOT_TAIL = 0xBB
GBOT_READ = 0x03


def gbot_packet(motor_id, cmd, data=()):
    data = list(data)
    chk = (motor_id + cmd + len(data) + sum(data)) & 0xFF
    return bytes([GBOT_HEADER, GBOT_HEADER, motor_id, cmd, len(data)] + data + [chk, GBOT_TAIL])


def gbot_parse(buf):
    """解析 AA AA 响应帧，返回 [(id, cmd, data_bytes), ...]"""
    out = []
    i = 0
    n = len(buf)
    while i + 7 <= n:
        if buf[i] != GBOT_HEADER or buf[i + 1] != GBOT_HEADER:
            i += 1
            continue
        mid, cmd, length = buf[i + 2], buf[i + 3], buf[i + 4]
        if length > 48 or i + 7 + length > n:
            i += 1
            continue
        data = buf[i + 5: i + 5 + length]
        if buf[i + 6 + length] != GBOT_TAIL:
            i += 1
            continue
        chk = (mid + cmd + length + sum(data)) & 0xFF
        if chk != buf[i + 5 + length]:
            i += 1
            continue
        out.append((mid, cmd, bytes(data)))
        i += 7 + length
    return out


# ---------------------------------------------------------------- 串口

def drain(ser, window=0.06):
    end = time.time() + window
    buf = bytearray()
    while time.time() < end:
        waiting = ser.in_waiting
        if waiting:
            buf += ser.read(waiting)
            end = time.time() + 0.02
        else:
            time.sleep(0.002)
    return bytes(buf)


def open_port(port, baud):
    ser = serial.Serial(port=port, baudrate=baud, bytesize=8, parity="N",
                        stopbits=1, timeout=0.02, write_timeout=0.1)
    time.sleep(0.05)
    ser.reset_input_buffer()
    return ser


def probe_ff(ser, ids):
    found = {}
    ser.reset_input_buffer()
    ser.write(ff_packet(0xFE, 1))          # PING，广播 ID
    ser.flush()
    for mid, err, params in ff_parse(drain(ser, 0.10)):
        found[mid] = params

    for mid in ids:
        if mid in found:
            continue
        ser.reset_input_buffer()
        ser.write(ff_packet(mid, 1))       # PING，单播
        ser.flush()
        for rid, err, params in ff_parse(drain(ser, 0.05)):
            found[rid] = params
    return found


def ff_read_position(ser, motor_id, width):
    """读 Present_Position（地址 56）。width=2 是 STS3215，width=4 是 Genki M1"""
    return ff_read_reg(ser, motor_id, 56, width)


def ff_read_reg(ser, motor_id, address, width):
    """读任意寄存器：INST_READ(2) + [地址, 字节数]"""
    ser.reset_input_buffer()
    ser.write(ff_packet(motor_id, 2, [address, width]))   # INST_READ
    ser.flush()
    for mid, err, params in ff_parse(drain(ser, 0.05)):
        if mid == motor_id and err == 0 and len(params) >= width:
            return int.from_bytes(params[:width], "little")
    return None


def probe_gbot(ser, ids):
    found = {}
    for mid in ids:
        ser.reset_input_buffer()
        ser.write(gbot_packet(mid, GBOT_READ, [7, 2]))   # CURRENT_POSITION
        ser.flush()
        for rid, cmd, data in gbot_parse(drain(ser, 0.06)):
            if rid == mid and cmd == GBOT_READ and len(data) >= 2:
                found[mid] = int.from_bytes(data[0:2], "little")
    return found


# ---------------------------------------------------------------- 官方 SDK 交叉验证

def sdk_probe(port, baud, ids):
    """用已安装的 scservo_sdk 打 ping。返回 {id: (protocol_end, model_number)}"""
    try:
        from scservo_sdk import COMM_SUCCESS, PacketHandler, PortHandler
    except Exception as e:
        print(f"    官方 SDK 不可用：{e}")
        return {}

    ph = PortHandler(port)
    if not ph.openPort():
        return {}
    ph.setBaudRate(baud)
    found = {}
    try:
        for endian in (0, 1):
            pkt = PacketHandler(endian)
            for mid in ids:
                try:
                    # 这个版本的 SDK 是 ping(port, id)，老版本是 ping(id)
                    try:
                        model, result, err = pkt.ping(ph, mid)
                    except TypeError:
                        model, result, err = pkt.ping(mid)
                except Exception:
                    continue
                if result == COMM_SUCCESS and model:
                    found[mid] = (endian, model)
    finally:
        ph.closePort()
    return found


# ---------------------------------------------------------------- 自检

def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    # 0xFF：ping 回包（LEN=2 -> 6 字节）
    reply = bytes([0xFF, 0xFF, 0x01, 0x02, 0x00, 0x00])
    reply = bytearray(reply)
    reply[-1] = ff_checksum([0x01, 0x02, 0x00])
    parsed = ff_parse(bytes(reply))
    check("FF ping 回包解析", parsed == [(1, 0, b"")])

    # 0xFF：读 2 字节位置回包（LEN=4 -> 8 字节）
    params = bytes([0x00, 0x34, 0x08])          # ERR=0, pos=0x0834=2100
    core = [0x06, 0x04] + list(params)
    frame = bytes([0xFF, 0xFF] + core + [ff_checksum(core)])
    parsed = ff_parse(frame)
    check("FF 2 字节位置回包解析", parsed == [(6, 0, bytes([0x34, 0x08]))])

    # GBot：读位置回包
    data = bytes([0x02, 0x08])
    chk = (0x03 + 0x03 + len(data) + sum(data)) & 0xFF
    gframe = bytes([0xAA, 0xAA, 0x03, 0x03, len(data)] + list(data) + [chk, 0xBB])
    parsed = gbot_parse(gframe)
    check("GBot 回包解析", parsed == [(3, 3, data)])

    # 校验和错了必须丢弃
    bad = bytearray(frame)
    bad[-1] ^= 0xFF
    check("坏校验和被丢弃", ff_parse(bytes(bad)) == [])

    print("  自检结果：", "全部通过" if ok else "有失败项")
    return 0 if ok else 1


# ---------------------------------------------------------------- 主流程

def describe_port(device):
    for p in list_ports.comports():
        if p.device.upper() == device.upper():
            return f"{p.description} [{p.hwid}]"
    return "(未在系统中找到该端口)"


def main():
    ap = argparse.ArgumentParser(description="探测串口上舵机的协议与波特率（只读，不驱动电机）")
    ap.add_argument("--ports", nargs="*", default=None)
    ap.add_argument("--bauds", nargs="*", type=int,
                    default=[1000000, 500000, 250000, 230400, 115200, 57600])
    ap.add_argument("--ids", nargs="*", type=int, default=list(range(1, 13)))
    ap.add_argument("--selftest", action="store_true", help="只跑解析器自检")
    ap.add_argument("--sdk", action="store_true", help="额外用官方 scservo_sdk 交叉验证")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    print("=" * 78)
    print("系统串口列表：")
    for p in list_ports.comports():
        print(f"  {p.device:<8} {p.description}  [{p.hwid}]")
    print("=" * 78)

    ports = args.ports or [p.device for p in list_ports.comports() if "BTHENUM" not in (p.hwid or "")]
    if not ports:
        print("没有找到任何串口。")
        return 1

    any_hit = False
    for port in ports:
        print(f"\n### {port}  {describe_port(port)}")
        for baud in args.bauds:
            try:
                ser = open_port(port, baud)
            except Exception as e:
                print(f"  baud={baud:<8} 打不开：{e}")
                continue

            try:
                ff = probe_ff(ser, args.ids)
                gb = probe_gbot(ser, args.ids)

                if ff:
                    ids_txt = ",".join(str(k) for k in sorted(ff))
                    print(f"  baud={baud:<8} [FF协议] 响应 ID: {ids_txt}")
                    first = sorted(ff)[0]
                    model = ff_read_reg(ser, first, 3, 2)     # Model_Number
                    fw = ff_read_reg(ser, first, 0, 2)        # Firmware
                    p2 = ff_read_position(ser, first, 2)
                    p4 = ff_read_position(ser, first, 4)
                    print(f"           ID {first}: 型号码={model} 固件={fw} "
                          f"位置(2字节)={p2} 位置(4字节)={p4}")
                    any_hit = True
                if gb:
                    ids_txt = ",".join(f"{k}(pos={v})" for k, v in sorted(gb.items()))
                    print(f"  baud={baud:<8} [AA协议] 响应 ID: {ids_txt}")
                    any_hit = True
                if not ff and not gb:
                    print(f"  baud={baud:<8} 无任何响应")
            finally:
                ser.close()

        if args.sdk:
            for baud in (1000000, 500000, 115200):
                sdk = sdk_probe(port, baud, args.ids[:8])
                if sdk:
                    print(f"  baud={baud:<8} [官方SDK] {sdk}")
                    any_hit = True
                else:
                    print(f"  baud={baud:<8} [官方SDK] 无响应")

    print("\n" + "=" * 78)
    if not any_hit:
        print("结论：所有端口 / 所有波特率 / 两种协议都没有回应。")
        print("  => 优先检查机械臂供电（只插 USB 是不够的）、总线线序和接头，")
        print("     以及这个 COM 口是否真的接的是那条臂。")
    else:
        print("结论：见上面有响应的那一行 —— 用它的协议和波特率去配 lerobot。")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
