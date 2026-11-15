# 主从遥操作（不依赖 lerobot）

`master_slave_teleop.py` 是一个**独立实现**的主从跟随：直接调用飞特 SDK 的
`GroupSyncRead` / `GroupSyncWrite`，把主端（leader）的实时位置映射到从端（follower）。

它的意义在于：不装 lerobot 也能验证硬件与跟随效果，并且**所有跟随参数都可调**——
调参经验可以直接搬到 lerobot 的遥操作里。

## 运行

```bash
# 需要 third_party/scservo_sdk（仓库已带，MIT）
python teleop/master_slave_teleop.py
```

串口找不到时会列出全部串口让你选；默认 `主端 COM5 / 从端 COM6`，1 Mbaud。

## 参数（脚本顶部「改这里」区块）

| 参数 | 含义 | 建议 |
|---|---|---|
| `JOINTS[].master/slave` | 主端读取 / 从端写入的舵机 ID | 通常 1:1 |
| `JOINTS[].scale` | `+1` 同向、`-1` 镜像 | 按装配方向定 |
| `JOINTS[].offset` | 中位补偿（位置单位 0–4095） | `offset = 主端位置 − 从端位置` |
| `JOINTS[].ratio` | 主从机械误差的比例校准 | 默认 1.0 |
| `FOLLOW_SPEED` / `FOLLOW_ACC` | 从端速度/加速度（0–2047 / 0–253） | 调低更稳、调高更跟手 |
| `DEADBAND` | 主从差小于该值不写，抑制抖动 | 1–3 |
| `LOWPASS` | 低通系数（0–1），滤掉手抖 | 0.7 |
| `POLL_INTERVAL` | 轮询周期（秒） | 0.03 → 约 30 Hz |

## 设计要点

- **同步读写**：一次 `txRxPacket()` 读 6 轴，一次 `txPacket()` 写 6 轴，
  避免逐轴往返造成的相位差（逐轴读会产生几十毫秒的关节间不同步）。
- **低通 + 死区**：串口读到的位置有量化抖动，直接照抄会让从端嗡嗡响。
- **绝对位置跟随**：不是增量控制，天然不会累积漂移；代价是主端的装配误差会整体传到从端
  （用 `offset` / `ratio` 补偿）。

## 局限

- 30 Hz 轮询，快速动作会略有滞后；
- 没有急停、限幅、watchdog——主端拔线后从端保持在最后位置（这点在 lerobot 版本里也一样，
  属于待补的安全层，见 [../docs/05-lessons.md](../docs/05-lessons.md)）。
