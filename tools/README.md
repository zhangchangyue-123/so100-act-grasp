# 硬件调试与数据整理工具

都是“上机前/调试时”用的小工具，不参与训练与推理。

| 脚本 | 用途 | 依赖 |
|---|---|---|
| `read_6_servos.py` | 终端里同步读 6 个舵机：原始位置 / 绝对角度 / 相对角度，刷新成一张表 | `third_party/scservo_sdk` |
| `servo_angle_monitor.py` | Tkinter GUI 监视器：串口选择、波特率切换、型号名、角度表格；后台线程读、UI 不卡 | Tkinter（Python 自带）+ SDK |
| `camer_read.py` | 打开相机，鼠标拖拽框选 ROI 并实时放大预览（用来核对视野/取景） | OpenCV |
| `json_to_txt.py` | 把 labelme 导出的 JSON 批量转成 txt（记录 path / size / 多边形点），便于整理标注统计 | 无 |

## 用法

```bash
python tools/read_6_servos.py                       # 交互式选串口
python tools/servo_angle_monitor.py                 # 图形界面
$env:CAMERA_INDEX = "2"; python tools/camer_read.py # 相机索引按机器改
$env:LABELME_DIR = "D:\labels\outputs"; python tools/json_to_txt.py
```

三个脚本都会自动把仓库里的 `third_party/` 加进 `sys.path`，
所以不需要 `pip install` 任何 SDK；如果你本机装过 `scservo_sdk`，也能直接走系统那份。

## 为什么留在仓库里

- **`read_6_servos.py`**：排查“舵机 ID 不对 / 某轴无响应”最快的手段，比跑整套 lerobot 快得多。
- **`servo_angle_monitor.py`**：GUI 里能一眼看出哪个关节在抖、哪个 ID 报错，
  是调 [../teleop/master_slave_teleop.py](../teleop/master_slave_teleop.py) 的配套工具。
- **`camer_read.py`**：确认相机装歪没歪、视野够不够——相机一旦动过，策略就会明显掉点。
- **`json_to_txt.py`**：早期做积木标注时的整理脚本，接 YOLO 自动评测会再用到。
