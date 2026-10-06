"""Agent.py -- 用 OpenAI 兼容接口（DeepSeek）生成今天的 2 小时学习计划。

流程：
    learning_project.txt -> model_input.parse_plan() -> 本周 + 下一个未计划的子任务
    -> Prompt.json（系统规则 + few-shot 示例）-> POST {OPENAI_BASE_URL}/chat/completions
    -> output/plan-<子任务>.json -> 刷新 output/reminder.md

运行：
    python Agent.py            # 当前周的下一个未计划子任务
    python Agent.py --day 3.2  # 指定子任务
    python Agent.py --no-save  # 只看结果，不写文件
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

from model_input import DATA_PATH, build_expected_input, parse_plan
from reminder import OUTPUT_DIR, load_plans, long_date, write_report

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
PROMPT_PATH = ROOT / "Prompt.json"

DEFAULT_TIMEOUT = 180
REQUIRED_FIELDS = ("day", "week_focus", "tasks", "log_reminder")


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #

def load_env(path: Path = ENV_PATH) -> None:
    """把 .env 读进 os.environ；已经存在的环境变量优先。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value and key not in os.environ:
            os.environ[key] = value


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} 没有设置 -- 请在 {ENV_PATH.name} 里填写。")
    return value


# --------------------------------------------------------------------------- #
# 调用模型
# --------------------------------------------------------------------------- #

def chat_json(base_url: str, api_key: str, model: str, messages: list, timeout: int) -> dict:
    """调用 OpenAI 兼容的 /chat/completions，返回模型给出的 JSON。"""
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        if exc.code in (401, 403):
            raise SystemExit(f"OPENAI_API_KEY 被拒绝（HTTP {exc.code}）：{detail}")
        raise SystemExit(f"接口返回 HTTP {exc.code}（model={model}）：{detail}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"连不上 {base_url}：{exc.reason}")
    except TimeoutError:
        raise SystemExit(f"接口超过 {timeout}s 没有响应（model={model}）。")

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise SystemExit(f"接口返回了意料之外的格式：\n{json.dumps(body, ensure_ascii=False, indent=2)}")

    return parse_json(content, model)


def parse_json(content: str, model: str) -> dict:
    """解析模型输出；有些网关会用 ```json 围栏包一层，这里剥掉。"""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise SystemExit(f"模型 {model} 没有返回合法 JSON：\n{content}")


def validate_plan(plan: dict) -> dict:
    """确认返回的 JSON 有我们需要的字段。"""
    if not isinstance(plan, dict):
        raise SystemExit(f"模型返回的不是 JSON 对象：{plan!r}")
    missing = [field for field in REQUIRED_FIELDS if field not in plan]
    if missing:
        raise SystemExit(
            f"模型返回的 JSON 缺少字段 {missing}：\n{json.dumps(plan, ensure_ascii=False, indent=2)}"
        )
    if not plan["tasks"]:
        raise SystemExit("模型返回的 tasks 是空的。")
    return plan


def build_messages(config: dict, expected_input: dict) -> list:
    """把 Prompt.json 变成 chat messages：系统规则 + few-shot 示例 + 本次输入。"""
    system = "\n".join([
        config["role"],
        "",
        "TASK",
        config["task"],
        "",
        "REQUIREMENTS",
        *[f"- {item}" for item in config["requirements"]],
        "",
        "OUTPUT FORMAT (JSON)",
        json.dumps(config["output_format"], ensure_ascii=False, indent=2),
        "",
        "Reply with a single JSON object and nothing else.",
    ])

    messages = [{"role": "system", "content": system}]
    for example in config.get("examples", []):
        messages.append({
            "role": "user",
            "content": json.dumps(example["expected_input"], ensure_ascii=False),
        })
        messages.append({
            "role": "assistant",
            "content": json.dumps(example["expected_output"], ensure_ascii=False),
        })
    messages.append({"role": "user", "content": json.dumps(expected_input, ensure_ascii=False)})
    return messages


# --------------------------------------------------------------------------- #
# 选周和子任务
# --------------------------------------------------------------------------- #

def week_for(weeks: dict, today: date) -> dict:
    """今天落在哪一周；超出计划范围就取第一周或最后一周。"""
    ordered = [weeks[number] for number in sorted(weeks)]
    for week in ordered:
        start, end = week["dates_start"], week["dates_end"]
        if start and end and start <= today <= end:
            return week
    if ordered and ordered[0]["dates_start"] and today < ordered[0]["dates_start"]:
        return ordered[0]
    return ordered[-1]


def find_task(weeks: dict, day_id: str):
    """按子任务 id（如 '3.2'）找到 (week, task)。"""
    for week in weeks.values():
        for task in week["tasks"]:
            if task["day"] == day_id:
                return week, task
    return None, None


def next_unplanned(weeks: dict, today: date, planned: set):
    """本周第一个还没生成过计划的子任务。"""
    week = week_for(weeks, today)
    remaining = [task for task in week["tasks"] if task["day"] not in planned]
    return week, (remaining[0] if remaining else None)


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #

def print_plan(record: dict) -> None:
    plan = record["plan"]
    print(f"\nWeek {record['week']} -- {record['week_focus']}"
          f"   (deadline {long_date(record['deadline'])})")
    print(f"Sub-task {record['day']}: {record['task']}\n")
    for task in plan.get("tasks", []):
        print(f"  {task.get('index', '?')}. [{task.get('duration_min', '?')} min] {task.get('name', '')}")
        print(f"     output:    {task.get('output', '')}")
        print(f"     done when: {task.get('done_criteria', '')}")
    print(f"\nREMINDER: {plan.get('log_reminder', '')}\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成今天的学习计划。")
    parser.add_argument("--day", help="指定子任务 id，例如 3.2（默认：本周下一个未计划的）")
    parser.add_argument("--date", type=date.fromisoformat,
                        help="把这一天当作今天，YYYY-MM-DD（默认：今天）")
    parser.add_argument("--model", help="覆盖 .env 里的 MODEL_NAME")
    parser.add_argument("--no-save", action="store_true", help="只打印，不写 output/")
    args = parser.parse_args(argv)

    load_env()
    base_url = require_env("OPENAI_BASE_URL")
    api_key = require_env("OPENAI_API_KEY")
    model = args.model or require_env("MODEL_NAME")
    timeout = int(os.environ.get("API_TIMEOUT", "") or DEFAULT_TIMEOUT)

    today = args.date or date.today()
    weeks = parse_plan(DATA_PATH)

    if args.day:
        week, task = find_task(weeks, args.day)
        if task is None:
            raise SystemExit(f"{DATA_PATH.name} 里没有子任务 {args.day!r}")
    else:
        week, task = next_unplanned(weeks, today, set(load_plans()))
        if task is None:
            raise SystemExit(
                f"Week {week['week']}（{week['focus']}）的子任务都已经有计划了，"
                "用 --day 指定新的子任务。"
            )

    expected_input = {
        "day": task["day"],
        "task": task["task"],
        "week_focus": week["focus"],
        **build_expected_input(week),
    }
    messages = build_messages(json.loads(PROMPT_PATH.read_text(encoding="utf-8")), expected_input)

    print(f"[plan] {today} -> Week {week['week']}, 子任务 {task['day']}: {task['task']}",
          file=sys.stderr)
    plan = validate_plan(chat_json(base_url, api_key, model, messages, timeout))

    record = {
        "date": today.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "week": week["week"],
        "week_focus": week["focus"],
        "deadline": week["deadline"].isoformat() if week["deadline"] else None,
        "day": task["day"],
        "task": task["task"],
        "plan": plan,
    }
    print_plan(record)

    if args.no_save:
        return 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"plan-{task['day']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[saved] {path}", file=sys.stderr)
    print(f"[report] {write_report()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
