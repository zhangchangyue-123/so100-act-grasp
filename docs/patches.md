# 对 lerobot / GenkiBot 的 4 处必要修复

本仓库不包含 lerobot 源码（Apache-2.0，体积大）。如果你从 upstream lerobot 或 GenkiBot fork 开始，
在 Windows + 本硬件环境下需要打下面这些补丁，否则会遇到对应故障。

---

## 补丁 1：找不到 `ffmpeg`，导致数据集只有 .pth 没有 mp4/meta_data

**现象**

```
FileNotFoundError: [WinError 2] 系统找不到指定的文件。
  subprocess.run(ffmpeg_cmd, check=True, stdin=subprocess.DEVNULL)
```
录完 50 条后 `episodes/*.pth` 和 `videos/*/frame_*.png` 都在，但 `videos/*.mp4`、`train/`、`meta_data/` 全没有。

**根因**：`lerobot/common/datasets/video_utils.py` 里直接调用 `["ffmpeg", ...]`，Windows 上通常不在 PATH；
且默认编码器 `libsvtav1` 在常见的 essentials 构建里**并不包含**（只有 `libaom-av1`，慢十倍以上）。

**修复**（`video_utils.py`）

```python
import shutil
from pathlib import Path

def get_ffmpeg_exe() -> str:
    """优先用 PATH 里的 ffmpeg，退回 imageio-ffmpeg 自带的静态二进制。"""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        cand = imageio_ffmpeg.get_ffmpeg_exe()
        if cand and Path(cand).exists():
            return cand
    except Exception:
        pass
    return "ffmpeg"

# encode_video_frames(...) 内
# vcodec 默认由 "libsvtav1" 改为 "libx264"
ffmpeg_cmd = [get_ffmpeg_exe()] + ffmpeg_args + [str(video_path)]
```

实测：x264 + `-g 2 -crf 30` 对 640×480 的 237 帧只需约 3 秒、1.3 MB（原始 PNG 约 50 MB）。

**已经录坏的数据怎么救**：`scripts/consolidate_dataset.py` 会读 `episodes/*.pth` + PNG 帧，
重建 mp4、`train/`、`meta_data/`；已存在的 mp4 会跳过，可重复运行。

---

## 补丁 2：OpenCV 打开 USB 相机要 5–28 秒，偶发静默崩溃

**现象**：`record` 卡在 `OpenCVCamera.connect()`（`cv2.set(CAP_PROP_FRAME_WIDTH)` 处抛 `KeyboardInterrupt`，
或进程无 traceback 直接消失），CPU 持续跑满。

**实测**（Windows + OpenCV 5.0.0 + 2 个 USB 相机）

| 后端 | index 0 | index 2 |
|---|---|---|
| MSMF（默认） | **28.5 s** | 5.4 s |
| DirectShow | **2.1 s** | 1.6 s |

**修复**（`lerobot/common/robot_devices/cameras/opencv.py`）

```python
def open_cv_camera(camera_idx, cv2_module=None):
    """Windows 上优先 DirectShow；失败再退回默认后端。"""
    cv2 = cv2_module
    if cv2 is None:
        import cv2
    if platform.system() == "Windows" and hasattr(cv2, "CAP_DSHOW"):
        cap = cv2.VideoCapture(camera_idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            return cap
        cap.release()
    return cv2.VideoCapture(camera_idx)
```

把 `connect()` 里两处 `cv2.VideoCapture(camera_idx)` 都换成 `open_cv_camera(camera_idx, cv2)`。

---

## 补丁 3：退出后舵机锁死，只能断电才能手动回位

**现象**：按 `ESC` 或跑完评估后，机械臂保持僵硬姿态，用手掰不动。

**根因**：`ManipulatorRobot.disconnect()` 只关串口，没有关闭力矩。

**修复**（`lerobot/common/robot_devices/robots/manipulator.py`）

```python
    def disconnect(self):
        ...
        # 关闭力矩再断开，否则舵机仍然锁死
        for name in self.follower_arms:
            try:
                self.follower_arms[name].write("Torque_Enable", 0)
            except Exception:
                pass
            self.follower_arms[name].disconnect()

        for name in self.leader_arms:
            try:
                self.leader_arms[name].write("Torque_Enable", 0)
            except Exception:
                pass
            self.leader_arms[name].disconnect()
```

验证：`connect()` 后 `Torque_Enable=[1,1,1,1,1,1]`，`disconnect()` 后再读为 `[0,0,0,0,0,0]`。

---

## 补丁 4：leader 臂用错驱动（`0xAA` 帧 vs `0xFF` 帧）

**现象**：`teleoperate` 时每帧都打印

```
Failed to write data 'Torque_Enable' to Motor '1' ... '6'
Failed to read data 'Present_Position' for Motor '1' ... '6'
```
循环掉到 2 Hz，`dtReadLeader ≈ 465 ms`。

**根因**：`so100.yaml` 里 leader 被配成 `GBotMotorsBus`（`0xAA 0xAA` 帧、力矩寄存器 50、目标位置 51），
但两条臂实际都是 **STS3215**（`0xFF 0xFF` 帧、40/42/56、1 Mbaud、型号码 777）。
用 `scripts/probe_servo_bus.py` 同时试探两种协议即可确认。

**修复**（`lerobot/configs/robot/so100.yaml`）

```yaml
leader_arms:
  main:
    _target_: lerobot.common.robot_devices.motors.feetech.FeetechMotorsBus
    port: com5
    motors:
      shoulder_pan:  [1, "sts3215"]
      shoulder_lift: [2, "sts3215"]
      elbow_flex:   [3, "sts3215"]
      wrist_flex:   [4, "sts3215"]
      wrist_roll:   [5, "sts3215"]
      gripper:      [6, "sts3215"]
```

另外两个 `GBot/port_handler.py` 的潜在 bug（本次未触发，但迟早会踩）：

- `read_timeout` / `write_timeout` 的 getter/setter 里 `return self.read_timeout` 无限递归；
- `gbot.py` 的 `are_motors_configured` / `find_motor_indices` / `set_bus_baudrate` 是 `pass` 空实现，
  标定流程依赖它们，所以走 `GBotMotorsBus` 这条路连校准都跑不通。
