#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""飞特 SMS/STS 系列舵机多路角度监视器。"""

from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


# 飞特 SDK 随仓库分发在 third_party/scservo_sdk。
SDK_DIR = Path(__file__).resolve().parent.parent / "third_party" / "scservo_sdk"
SDK_PARENT = SDK_DIR.parent
if SDK_PARENT.is_dir() and str(SDK_PARENT) not in sys.path:
    sys.path.insert(0, str(SDK_PARENT))

SDK_IMPORT_ERROR: Exception | None = None
try:
    import serial.tools.list_ports
    from scservo_sdk import (  # type: ignore
        COMM_SUCCESS,
        GroupSyncRead,
        PortHandler,
        SMS_STS_PRESENT_POSITION_L,
        sms_sts,
    )
except (ImportError, ModuleNotFoundError) as exc:
    SDK_IMPORT_ERROR = exc


BAUDRATES = {
    "1M（默认）": 1_000_000,
    "500K": 500_000,
    "250K": 250_000,
    "128K": 128_000,
    "115200": 115_200,
    "57600": 57_600,
    "38400": 38_400,
}

MODEL_NAMES = {
    0x0806: "STS3215",
    0x0805: "STS3020",
    0x0804: "STS3032",
    0x0807: "STS3046",
    0x0803: "STS3009",
    0x0801: "STS2000",
    0x0504: "SM40BL",
    0x0505: "SM60CL",
    0x0506: "SM85CL",
    0x0503: "SM30BL",
    0x0808: "STS3215（新版）",
    0x0309: "STS3009",
}

COUNTS_PER_REVOLUTION = 4096
POSITION_DATA_LENGTH = 2


def position_to_angles(position: int, zero_position: int) -> tuple[float, float]:
    """把 0~4095 位置值换算成绝对角度和以 zero_position 为零点的角度。"""
    absolute = (position % COUNTS_PER_REVOLUTION) * 360.0 / COUNTS_PER_REVOLUTION
    relative = (
        (position - zero_position) * 360.0 / COUNTS_PER_REVOLUTION + 180.0
    ) % 360.0 - 180.0
    return absolute, relative


class ServoAngleMonitorApp:
    """串口连接、舵机扫描和多路角度实时显示界面。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("飞特舵机多路角度监视器")
        self.root.geometry("820x600")
        self.root.minsize(720, 500)

        self.port_handler = None
        self.packet_handler = None
        self.servo_ids: list[int] = []
        self.servo_models: dict[int, str] = {}
        self.row_ids: dict[int, str] = {}

        self.io_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.events: queue.Queue[tuple] = queue.Queue()
        self.session_id = 0
        self.worker: threading.Thread | None = None
        self.connected = False
        self.scanning = False
        self.poll_interval_ms = 200

        self.port_var = tk.StringVar()
        self.baudrate_var = tk.StringVar(value="1M（默认）")
        self.scan_start_var = tk.IntVar(value=1)
        self.scan_end_var = tk.IntVar(value=20)
        self.zero_position_var = tk.IntVar(value=2048)
        self.interval_var = tk.IntVar(value=200)
        self.interval_var.trace_add("write", self._update_poll_interval)
        self.status_var = tk.StringVar(value="就绪：请选择串口")
        self.count_var = tk.StringVar(value="已发现：0 个舵机")

        self._build_ui()
        self._refresh_ports()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._process_events)

    def _build_ui(self) -> None:
        title = ttk.Frame(self.root, padding=(12, 10, 12, 4))
        title.pack(fill=tk.X)
        ttk.Label(
            title,
            text="SMS / STS 舵机实时角度",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Label(title, textvariable=self.count_var).pack(side=tk.RIGHT, pady=(7, 0))

        connection = ttk.LabelFrame(self.root, text="连接设置", padding=10)
        connection.pack(fill=tk.X, padx=12, pady=6)

        ttk.Label(connection, text="串口").grid(row=0, column=0, sticky=tk.W)
        self.port_combo = ttk.Combobox(
            connection, textvariable=self.port_var, state="readonly", width=18
        )
        self.port_combo.grid(row=0, column=1, padx=(6, 4), sticky=tk.EW)
        self.refresh_button = ttk.Button(
            connection, text="刷新", width=7, command=self._refresh_ports
        )
        self.refresh_button.grid(row=0, column=2, padx=(0, 14))

        ttk.Label(connection, text="波特率").grid(row=0, column=3, sticky=tk.W)
        self.baud_combo = ttk.Combobox(
            connection,
            textvariable=self.baudrate_var,
            values=list(BAUDRATES),
            state="readonly",
            width=13,
        )
        self.baud_combo.grid(row=0, column=4, padx=6)

        self.connect_button = ttk.Button(
            connection, text="连接", command=self._connect, width=10
        )
        self.connect_button.grid(row=0, column=5, padx=(12, 4))
        self.disconnect_button = ttk.Button(
            connection,
            text="断开",
            command=self._disconnect,
            width=10,
            state=tk.DISABLED,
        )
        self.disconnect_button.grid(row=0, column=6)
        connection.columnconfigure(1, weight=1)

        options = ttk.LabelFrame(self.root, text="扫描与角度设置", padding=10)
        options.pack(fill=tk.X, padx=12, pady=6)

        ttk.Label(options, text="扫描 ID").grid(row=0, column=0, sticky=tk.W)
        self.start_spin = ttk.Spinbox(
            options, from_=0, to=253, textvariable=self.scan_start_var, width=6
        )
        self.start_spin.grid(row=0, column=1, padx=(6, 2))
        ttk.Label(options, text="至").grid(row=0, column=2)
        self.end_spin = ttk.Spinbox(
            options, from_=0, to=253, textvariable=self.scan_end_var, width=6
        )
        self.end_spin.grid(row=0, column=3, padx=(2, 16))

        ttk.Label(options, text="相对角零点").grid(row=0, column=4, sticky=tk.W)
        self.zero_spin = ttk.Spinbox(
            options,
            from_=0,
            to=4095,
            textvariable=self.zero_position_var,
            width=8,
        )
        self.zero_spin.grid(row=0, column=5, padx=(6, 16))

        ttk.Label(options, text="刷新间隔").grid(row=0, column=6, sticky=tk.W)
        self.interval_spin = ttk.Spinbox(
            options,
            from_=50,
            to=5000,
            increment=50,
            textvariable=self.interval_var,
            width=8,
        )
        self.interval_spin.grid(row=0, column=7, padx=(6, 2))
        ttk.Label(options, text="ms").grid(row=0, column=8, sticky=tk.W)

        self.scan_button = ttk.Button(
            options,
            text="扫描舵机",
            command=self._start_scan,
            state=tk.DISABLED,
        )
        self.scan_button.grid(row=0, column=9, padx=(18, 0))

        table_frame = ttk.LabelFrame(self.root, text="实时数据", padding=6)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        columns = ("id", "model", "position", "absolute", "relative", "state")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", height=14
        )
        headings = {
            "id": "舵机 ID",
            "model": "型号",
            "position": "原始位置",
            "absolute": "绝对角度",
            "relative": "相对角度",
            "state": "通信状态",
        }
        widths = {
            "id": 75,
            "model": 155,
            "position": 100,
            "absolute": 115,
            "relative": 115,
            "state": 125,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        hint = (
            "换算：4096 个位置单位 = 360°；绝对角度范围 0~360°，"
            "相对角度范围 -180~+180°。"
        )
        ttk.Label(self.root, text=hint, foreground="#666666").pack(
            fill=tk.X, padx=14, pady=(0, 5)
        )
        ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=5,
        ).pack(fill=tk.X, side=tk.BOTTOM)

    def _refresh_ports(self) -> None:
        if SDK_IMPORT_ERROR is not None:
            self.port_combo["values"] = ()
            self.port_var.set("")
            self.status_var.set("缺少 SDK 或 pyserial，无法获取串口")
            return

        ports = sorted(
            serial.tools.list_ports.comports(),
            key=lambda item: item.device.lower(),
        )
        devices = [port.device for port in ports]
        previous = self.port_var.get()
        self.port_combo["values"] = devices
        if previous in devices:
            self.port_var.set(previous)
        elif devices:
            self.port_combo.current(0)
        else:
            self.port_var.set("")
            self.status_var.set("未发现串口，请连接 URT-1 后刷新")

    def _connect(self) -> None:
        if SDK_IMPORT_ERROR is not None:
            messagebox.showerror(
                "依赖加载失败",
                f"无法加载飞特 SDK 或 pyserial：\n{SDK_IMPORT_ERROR}\n\n"
                f"SDK 路径：{SDK_DIR}",
            )
            return

        port_name = self.port_var.get().strip()
        if not port_name:
            messagebox.showwarning("提示", "请先选择串口。")
            return

        baudrate = BAUDRATES.get(self.baudrate_var.get(), 1_000_000)
        candidate = None
        try:
            candidate = PortHandler(port_name)
            if not candidate.openPort():
                raise OSError(f"无法打开串口 {port_name}")
            if not candidate.setBaudRate(baudrate):
                raise OSError(f"无法设置波特率 {baudrate}")
            packet_handler = sms_sts(candidate)
        except Exception as exc:
            if candidate is not None:
                try:
                    candidate.closePort()
                except Exception:
                    pass
            messagebox.showerror("连接失败", f"无法连接 {port_name}：\n{exc}")
            return

        self.session_id += 1
        self.stop_event.clear()
        self.port_handler = candidate
        self.packet_handler = packet_handler
        self.connected = True
        self.servo_ids.clear()
        self.servo_models.clear()
        self._clear_table()
        self._set_connected_controls(True)
        self.status_var.set(f"已连接 {port_name} @ {baudrate}，请扫描舵机")

    def _disconnect(self) -> None:
        if not self.connected and self.port_handler is None:
            return

        self.session_id += 1
        self.stop_event.set()
        self.connected = False
        self.scanning = False

        with self.io_lock:
            if self.port_handler is not None:
                try:
                    self.port_handler.closePort()
                except Exception:
                    pass
        self.port_handler = None
        self.packet_handler = None
        self.servo_ids.clear()
        self.servo_models.clear()
        self._clear_table()
        self._set_connected_controls(False)
        self.status_var.set("串口已断开")

    def _start_scan(self) -> None:
        if not self.connected or self.packet_handler is None:
            return

        try:
            first_id = int(self.scan_start_var.get())
            last_id = int(self.scan_end_var.get())
        except (tk.TclError, ValueError):
            messagebox.showwarning("参数错误", "扫描 ID 必须是整数。")
            return
        if not 0 <= first_id <= 253 or not 0 <= last_id <= 253:
            messagebox.showwarning("参数错误", "舵机 ID 范围必须在 0~253。")
            return
        if first_id > last_id:
            messagebox.showwarning("参数错误", "起始 ID 不能大于结束 ID。")
            return

        self.stop_event.set()
        self.stop_event = threading.Event()
        self.scanning = True
        self.servo_ids.clear()
        self.servo_models.clear()
        self._clear_table()
        self.scan_button.configure(state=tk.DISABLED)
        self.status_var.set(f"正在扫描 ID {first_id}~{last_id}…")

        session = self.session_id
        self.worker = threading.Thread(
            target=self._scan_worker,
            args=(session, first_id, last_id, self.stop_event),
            daemon=True,
        )
        self.worker.start()

    def _scan_worker(
        self,
        session: int,
        first_id: int,
        last_id: int,
        stop_event: threading.Event,
    ) -> None:
        found: list[tuple[int, int]] = []
        total = last_id - first_id + 1
        try:
            for index, servo_id in enumerate(range(first_id, last_id + 1), start=1):
                if stop_event.is_set() or session != self.session_id:
                    return
                with self.io_lock:
                    if self.packet_handler is None:
                        return
                    model, result, error = self.packet_handler.ping(servo_id)
                if result == COMM_SUCCESS and error == 0:
                    found.append((servo_id, model))
                self.events.put((session, "scan_progress", servo_id, index, total))
        except Exception as exc:
            self.events.put((session, "worker_error", f"扫描中断：{exc}"))
            return
        self.events.put((session, "scan_done", found, stop_event))

    def _start_monitor(
        self, session: int, stop_event: threading.Event
    ) -> None:
        self.worker = threading.Thread(
            target=self._monitor_worker,
            args=(session, stop_event),
            daemon=True,
        )
        self.worker.start()

    def _monitor_worker(
        self, session: int, stop_event: threading.Event
    ) -> None:
        if self.packet_handler is None:
            return

        sync_reader = GroupSyncRead(
            self.packet_handler,
            SMS_STS_PRESENT_POSITION_L,
            POSITION_DATA_LENGTH,
        )
        for servo_id in self.servo_ids:
            sync_reader.addParam(servo_id)

        while not stop_event.is_set() and session == self.session_id:
            readings: dict[int, tuple[int | None, str]] = {}
            try:
                with self.io_lock:
                    if self.packet_handler is None:
                        return
                    result = sync_reader.txRxPacket()
                    for servo_id in self.servo_ids:
                        available, error = sync_reader.isAvailable(
                            servo_id,
                            SMS_STS_PRESENT_POSITION_L,
                            POSITION_DATA_LENGTH,
                        )
                        # 某一个舵机掉线时，同步读取的总体结果可能不是成功；
                        # 仍应保留已经完整收到的其他舵机数据。
                        if available and error == 0:
                            raw = sync_reader.getData(
                                servo_id,
                                SMS_STS_PRESENT_POSITION_L,
                                POSITION_DATA_LENGTH,
                            )
                            position = self.packet_handler.scs_tohost(raw, 15)
                            readings[servo_id] = (position, "正常")
                        elif error:
                            readings[servo_id] = (None, f"舵机错误 0x{error:02X}")
                        else:
                            readings[servo_id] = (None, "无响应")
                self.events.put((session, "readings", readings))
            except Exception as exc:
                self.events.put((session, "worker_error", f"读取中断：{exc}"))
                return

            stop_event.wait(self.poll_interval_ms / 1000.0)

    def _process_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                session, event_type, *payload = event
                if session != self.session_id:
                    continue

                if event_type == "scan_progress":
                    servo_id, index, total = payload
                    self.status_var.set(
                        f"正在扫描 ID {servo_id}（{index}/{total}）…"
                    )
                elif event_type == "scan_done":
                    found, stop_event = payload
                    self._finish_scan(session, found, stop_event)
                elif event_type == "readings":
                    self._show_readings(payload[0])
                elif event_type == "worker_error":
                    self.scanning = False
                    if self.connected:
                        self.scan_button.configure(state=tk.NORMAL)
                    self.status_var.set(payload[0])
        except queue.Empty:
            pass
        finally:
            if self.root.winfo_exists():
                self.root.after(50, self._process_events)

    def _finish_scan(
        self,
        session: int,
        found: list[tuple[int, int]],
        stop_event: threading.Event,
    ) -> None:
        self.scanning = False
        if not self.connected or stop_event.is_set():
            return

        self.servo_ids = [servo_id for servo_id, _model in found]
        self.servo_models = {
            servo_id: MODEL_NAMES.get(model, f"未知型号（0x{model:04X}）")
            for servo_id, model in found
        }
        self._clear_table()
        for servo_id in self.servo_ids:
            row_id = self.tree.insert(
                "",
                tk.END,
                values=(
                    servo_id,
                    self.servo_models[servo_id],
                    "--",
                    "--",
                    "--",
                    "等待读取",
                ),
            )
            self.row_ids[servo_id] = row_id

        count = len(self.servo_ids)
        self.count_var.set(f"已发现：{count} 个舵机")
        self.scan_button.configure(state=tk.NORMAL)
        if count:
            self.status_var.set(f"扫描完成，正在监视 {count} 个舵机")
            self._start_monitor(session, stop_event)
        else:
            self.status_var.set("扫描完成，未发现舵机；请检查接线、ID 和波特率")

    def _show_readings(self, readings: dict[int, tuple[int | None, str]]) -> None:
        try:
            zero_position = max(0, min(4095, int(self.zero_position_var.get())))
        except (tk.TclError, ValueError):
            zero_position = 2048

        normal_count = 0
        for servo_id, (position, state) in readings.items():
            row_id = self.row_ids.get(servo_id)
            if row_id is None:
                continue
            if position is None:
                values = (
                    servo_id,
                    self.servo_models.get(servo_id, "--"),
                    "--",
                    "--",
                    "--",
                    state,
                )
            else:
                absolute, relative = position_to_angles(position, zero_position)
                values = (
                    servo_id,
                    self.servo_models.get(servo_id, "--"),
                    position,
                    f"{absolute:.2f}°",
                    f"{relative:+.2f}°",
                    state,
                )
                normal_count += 1
            self.tree.item(row_id, values=values)

        self.status_var.set(
            f"实时监视中：{normal_count}/{len(self.servo_ids)} 个舵机通信正常"
        )

    def _set_connected_controls(self, connected: bool) -> None:
        self.connect_button.configure(state=tk.DISABLED if connected else tk.NORMAL)
        self.disconnect_button.configure(state=tk.NORMAL if connected else tk.DISABLED)
        self.scan_button.configure(state=tk.NORMAL if connected else tk.DISABLED)
        self.port_combo.configure(state=tk.DISABLED if connected else "readonly")
        self.baud_combo.configure(state=tk.DISABLED if connected else "readonly")
        self.refresh_button.configure(state=tk.DISABLED if connected else tk.NORMAL)

    def _update_poll_interval(self, *_args) -> None:
        """只在 Tk 主线程读取界面变量，工作线程读取普通整数。"""
        try:
            self.poll_interval_ms = max(
                50, min(5000, int(self.interval_var.get()))
            )
        except (tk.TclError, ValueError):
            pass

    def _clear_table(self) -> None:
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self.row_ids.clear()
        self.count_var.set("已发现：0 个舵机")

    def _on_close(self) -> None:
        self.stop_event.set()
        self.session_id += 1
        with self.io_lock:
            if self.port_handler is not None:
                try:
                    self.port_handler.closePort()
                except Exception:
                    pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ServoAngleMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
