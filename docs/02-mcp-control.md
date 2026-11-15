# 语言控制线：DeepSeek + MCP

## 1. 架构

```
你（终端输入）
   │
   ▼
chat_client.py ── list_tools ──► mcp_server.py（FastMCP，SSE @ localhost:8000）
   │                                   │
   │  tools 转成 OpenAI function-calling 格式
   ▼                                   │
DeepSeek API（deepseek-chat）           │  被选中时执行
   │  tool_calls                       │
   └───────────────────────────────────┘
                              ├─ add / sub / mul / div
                              ├─ file_search        按文件名搜 D 盘
                              ├─ set_student_servo_angles(6 轴) ─► 串口 1 Mbaud ─► STS3215
                              ├─ set_student_servo_angle(单轴)
                              └─ tts_speak          离线朗读（pyttsx3）
```

客户端做的事：`list_tools` → 转成 `{"type":"function", ...}` → 调模型 → 若返回 `tool_calls`
就逐个执行并把结果作为 `role=tool` 消息回填 → 循环到模型给出最终文本。

## 2. 七个工具

| 工具 | 参数 | 说明 |
|---|---|---|
| `add` / `sub` / `mul` / `div` | `a, b` | 最小验证，用来确认工具调用链路通 |
| `file_search` | `pattern, start, exact, case_sensitive, first, exclude` | 按文件名遍历搜索，默认从 `D:\` 开始 |
| `set_student_servo_angles` | `angles[6], port="COM7", baudrate=1000000` | 六轴一起设，−90°…+90° |
| `set_student_servo_angle` | `servo_id, angle, port="COM12"` | 单轴微调 |
| `tts_speak` | `text, language_hint, voice_id, rate, volume` | 离线朗读 |

系统提示词里定义了关节语义：**1 号腰、2 号大臂、3 号小臂、4/5 号腕、6 号夹爪**，
所以“把夹爪张开”“手臂抬一点”能被正确映射到具体 ID。

## 3. 运行

```bash
# 终端 1：服务端（SSE，默认 8000）
python src/mcp_server.py

# 终端 2：客户端
$env:DEEPSEEK_API_KEY = "sk-..."     # 必须用环境变量，仓库不含密钥
python src/chat_client.py
```

可以试这几句：`3+5=?`、`帮我在 D 盘找一下 *.pdf`、`把夹爪张开到 30 度`、`讲个故事再读出来`。

## 4. 这条线的局限（也是下一步的入口）

- **开环、无反馈**：模型只能“发角度”，读不到当前姿态，看不到相机。
- **没有安全层**：没有速度/幅度限幅，指令越界只做 clamp。
- **单步技能，没有任务规划**：不会“先抓红块再放蓝块”这种组合任务。

升级方向（端侧具身 agent）：本地 VLM 出任务规划 → 调用技能层（ACT 策略作为一个 skill）→
失败检测与重试。这样它就从“遥控器”变成“会分解任务的大脑”，并且可以整体离线跑在 Jetson 上。
