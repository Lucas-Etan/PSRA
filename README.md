# PSRA — 个人学习提醒助手

把一个 16 周的 Python 学习计划，变成**每天一份可执行的 2 小时计划**和**每周一张进度表**，
并且可以接入飞书——在群里 @ 一下机器人就能拿到。

## 它做什么

1. 读 `learning_project.txt` 里的 16 周计划（每周有主题、交付物、若干子任务）
2. 按日期定位到**当前周**和**下一个还没生成过计划的子任务**
3. 调用大模型把这个子任务拆成 **4 个 30 分钟的具体任务**，每个都带明确产出和完成标准
4. 把已生成的所有计划汇总成 `output/reminder.md`——**每周一张表**，表格最后一行是提醒

## 工作流程

```
learning_project.txt
   │  model_input.parse_plan()        解析周次 / 主题 / 交付物 / 子任务 / 日期
   ▼
本周 + 下一个未计划的子任务
   │  Prompt.json                     系统规则 + 两个 few-shot 示例
   ▼
OpenAI 兼容接口  POST {OPENAI_BASE_URL}/chat/completions
   ▼
output/plan-<子任务>.json              每个子任务一份，落盘
   │  reminder.build_report()
   ▼
output/reminder.md                     每周一张表 + 提醒行
```

## 目录结构

| 文件 | 作用 |
| --- | --- |
| `main.py` | 入口。生成今日计划 + 显示提醒表 |
| `Agent.py` | 选周选子任务、组装 prompt、调用模型、保存计划 |
| `reminder.py` | 读 `output/`，汇总成每周一张 markdown 表 |
| `model_input.py` | 解析 `learning_project.txt`（含日期和截止日期） |
| `Prompt.json` | 系统提示 + 输出格式 + few-shot 示例 |
| `learning_project.txt` | 学习计划原文（数据源） |
| `.env` | 接口地址和密钥（**已 gitignore**） |
| `output/` | 生成的计划与提醒表（**已 gitignore**） |

只用 Python 标准库，没有任何第三方依赖。

## 快速开始

```bash
# 1. 准备 Python 3.11+

# 2. 配置 .env

# 3. 生成今天的学习计划，并显示本周的表
python main.py
```

## 环境变量

写在项目根目录的 `.env` 里：

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `OPENAI_BASE_URL` | 是 | OpenAI 兼容接口地址，例如 `https://api.deepseek.com` |
| `OPENAI_API_KEY` | 是 | API 密钥 |
| `MODEL_NAME` | 是 | 模型 id，例如 `deepseek-v4-flash` |
| `API_TIMEOUT` | 否 | 请求超时秒数，默认 180 |

`.env` 已经在 `.gitignore` 里，不会被提交。**不要把密钥写进代码或提交到仓库。**

## 用法

### main.py

```bash
python main.py                     # 生成今天的学习计划 + 显示本周的表
python main.py --reminder          # 不调用模型，只看提醒表（纯本地，秒回、免费）
python main.py --all-weeks         # 显示全部 16 周的表
python main.py --week 3            # 只看第 3 周
python main.py --day 3.2           # 指定子任务
python main.py --date 2026-10-20   # 把某一天当作"今天"
python main.py --no-save           # 只打印，不写文件
```

### 单独运行各模块

```bash
python reminder.py                 # 只刷新并显示提醒表（不需要 API key）
python reminder.py --week 3        # 只显示第 3 周
python model_input.py              # 查看解析结果，调试用
```

### 子任务是怎么选的

- **哪一周**：按 `learning_project.txt` 里每周的起止日期判断；超出范围就取第一周或最后一周
- **哪个子任务**：当前周里**第一个在 `output/` 中没有计划文件**的
- 所以重复运行会依次推进到下一个子任务，而不是重复生成同一个

## 输出

### `output/plan-<子任务>.json`

每个子任务一份，重复生成会覆盖：

```json
{
  "date": "2026-10-06",
  "generated_at": "2026-10-06T23:04:20",
  "model": "deepseek-v4-flash",
  "week": 1,
  "week_focus": "Environment & first programs",
  "deadline": "2026-10-12",
  "day": "1.1",
  "task": "Install Python 3.12+ and verify with `python --version`",
  "plan": {
    "day": "1.1",
    "week_focus": "Environment & first programs",
    "tasks": [
      {
        "index": 1,
        "name": "Download Python 3.12 installer",
        "duration_min": 30,
        "output": "Python 3.12 installer downloaded to local machine",
        "done_criteria": "Installer file exists and version is 3.12.x"
      }
    ],
    "log_reminder": "Please submit your study log now: ..."
  }
}
```

### `output/reminder.md`

每周一张 markdown 表，列出该周所有子任务、计划任务和交付物；**最后一行是提醒**：

| Sub-task | Task | Planned tasks | Deliverables |
| --- | --- | --- | --- |
| 1.1 | Install Python 3.12+ … | 1. Download Python 3.12 installer<br>2. … | 1. Python 3.12 installer downloaded…<br>2. … |
| 1.2 | Set up an editor/IDE … | `--` | `--` |
| ⏰ | **REMINDER** | Submit your study log (1 of 6 sub-tasks planned so far). | Due **Monday, October 12, 2026**. |

还没生成计划的子任务显示 `--`，所以这张表同时也是一个进度视图。

## 接入飞书（通过 OpenClaw）

除了命令行，这个项目也可以接到飞书——在群里 @ 机器人，让它跑脚本并把结果发回来。
这部分的配置在 OpenClaw 侧，不在本仓库：

- **Skill 文件**：`~/.openclaw/workspace/skills/psra-reminder/SKILL.md`
- **Agent**：`main`，模型用 `deepseek/deepseek-v4-flash`
- **飞书通道**：OpenClaw 的 `default` 账号，路由到 agent `main`

Skill 里写死了本项目的绝对路径，所以 OpenClaw 必须和本项目跑在同一台机器上。
验证 skill 是否被识别：

```bash
openclaw skills list --agent main | grep psra
openclaw channels status --probe
```

几个已经踩过的坑，改动前值得知道：

- 群聊要能触发机器人，群必须在 `channels.feishu.accounts.default.groupAllowFrom` 里
- 斜杠命令的授权是**独立**的一层，靠 `allowFrom`（发送者白名单），与群白名单无关
- **本地小模型（7B）无法可靠地路由到 skill**——它会在一次迭代内直接回话，不调用任何工具。用 DeepSeek 这类模型才稳

## 注意事项

- `model_input.py` 依赖 `learning_project.txt` 的格式（`WEEK N -- 主题`、缩进的 `N.M 子任务 (X.X h)`、`Dates` / `Deadline` 行）。改计划文件时保持这个格式，否则解析会静默丢字段。
- `main.py` 不带 `--reminder` 时会**调用模型并推进进度**；只想看现状就用 `--reminder`。
- 生成的计划会覆盖同子任务 id 的旧文件，没有版本历史。
