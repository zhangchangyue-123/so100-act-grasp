# 从采集到评估：完整流程

前置：已获取 lerobot fork 并打好 [patches.md](patches.md) 里的补丁，工作目录为 `genkiarm/`。
下文命令均在 Windows PowerShell 下验证过。

---

## 0. 开跑前 30 秒体检（强烈建议）

```powershell
python D:\...\scripts\probe_servo_bus.py --ports COM5 COM6 --sdk   # 型号应为 777、1 Mbaud
python D:\...\scripts\probe_cameras.py                             # 确认 0=侧视, 2=俯视
python D:\...\scripts\check_robot_connect.py                       # 连两臂 + 读一帧 + 读角度（不动作）
```

---

## 1. 采集演示（遥操作）

```powershell
python lerobot/scripts/control_robot.py record `
  --robot-path lerobot/configs/robot/so100.yaml `
  --fps 30 --root data --repo-id pick/so100_test `
  --warmup-time-s 3 --episode-time-s 30 --reset-time-s 6 --num-episodes 50 `
  --run-compute-stats 0 --push-to-hub 0 --force-override 1
```

要点：

- **`--num-episodes` 是“这个 repo 里累计到几集就停”**，不是“再录几集”。复用同一个 `--repo-id` 会立刻退出（机械臂一动不动）。
  用 `--force-override 1` 清空重录，或每次换 id。
- 抓完就按 **→** 提前结束该轮，别录进大段静止画面（本项目 50 条中位数 8.2 秒）。
- 每条都从**同一个折叠起始姿态**开始，抓稳→放进纸盒→回位，一套动作走完。
- 键盘：`→` 结束当前回合 / `←` 重录 / `ESC` 全部停止。

采集结束后如果 `videos/` 里只有 PNG 帧、没有 mp4 和 `meta_data/`（ffmpeg 缺失的典型症状），
先看 [patches.md](patches.md) 第 1 条，再用 `scripts/consolidate_dataset.py` 补齐：

```powershell
python ...\scripts\consolidate_dataset.py --repo-id pick/so100_test --root data
```

---

## 2. 训练（ACT）

```powershell
$env:DATA_DIR = "./data/"
python lerobot/scripts/train.py `
  dataset_repo_id=pick/so100_test policy=act_so100_real env=so100_real `
  hydra.run.dir=outputs/train/act_so100_50eps hydra.job.name=act_so100_50eps `
  device=cuda wandb.enable=false `
  training.batch_size=8 training.offline_steps=40000
```

实测（RTX 4060 Laptop 8 GB）：batch 8 峰值显存 5.7 GB，约 **0.34 s/步**，40k 步 3 小时 47 分。

想判断“要不要继续训”，用跨 checkpoint 的误差对比（不动机械臂，几十秒）：

```powershell
python ...\scripts\check_convergence.py
# 本项目：10k 0.0957 → 20k 0.0713 → 30k 0.0605 → 40k 0.0545，未平台期 → 应续训
```

续训（`resume=true` 会读 checkpoint 内配置并忽略命令行覆盖，需先改文件里的步数）：

```powershell
notepad outputs\train\act_so100_50eps\checkpoints\last\pretrained_model\config.yaml  # offline_steps: 40000 -> 100000
python lerobot/scripts/train.py resume=true hydra.run.dir=outputs/train/act_so100_50eps
```

---

## 3. 真机评估（策略自主执行）

```powershell
python lerobot/scripts/control_robot.py record `
  --robot-path lerobot/configs/robot/so100.yaml `
  --fps 30 --root data --repo-id pick/eval_long20 `
  --warmup-time-s 3 --episode-time-s 20 --reset-time-s 8 --num-episodes 15 `
  --run-compute-stats 0 --push-to-hub 0 --force-override 1 `
  --policy-overrides "policy.n_action_steps=10" `
  -p outputs/train/act_so100_50eps/checkpoints/last/pretrained_model
```

四个必须的理由：

| 参数 | 为什么 |
|---|---|
| `--repo-id ... eval_` 开头 | 带 `-p` 时数据集名**必须**以 `eval_` 开头，否则直接 `ValueError` |
| `--run-compute-stats 0` | 默认会在结束时做两遍全量解码算统计量（实测 27 分钟），评估不需要 |
| `--push-to-hub 0` | 默认会上传 HuggingFace，没登录会在演示结束后才报错 |
| `policy.n_action_steps=10` | 默认 100 步盲执行（3.3 s 不重新观察）会漂移；改成每 10 步重规划，成功率 20% → 47–67% |

`--episode-time-s` 别设太短：演示中位数 8.2 s，但策略执行比演示慢，10 s 常常只够“碰到积木”。

---

## 4. 出指标

```powershell
python ...\scripts\summarize_eval.py --folder data\pick\eval_long20   # 动作形态表 + 末帧拼图
python ...\scripts\compare_speed.py                                  # 演示 vs 策略的节奏对比
python ...\scripts\export_metrics.py                                 # l1 / 逐关节 MAE（度）
python ...\scripts\measure_latency.py                                # 单次推理延迟（端侧基线）
```

`summarize_eval.py` 的判定口径：大臂最低点 > −30° 记“没动”；下探后结束角 < 50° 记“只下探没回位”；
其余记“下探+回位”。它只是动作形态，**是否真的抓住要靠拼图目视核对**（脚本会一并导出末帧图）。
