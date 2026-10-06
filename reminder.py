"""reminder.py -- 把生成的学习计划汇总成"每周一张表"的提醒报告。

读取 output/plan-*.json（Agent.py 生成），按周分组，写出 output/reminder.md：
每周一张 markdown 表，列出该周的子任务、计划任务、交付物，最后一行是提醒。

也可以单独运行：
    python reminder.py            # 全部 16 周
    python reminder.py --week 3   # 只看第 3 周
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from model_input import DATA_PATH, parse_plan

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
REPORT_PATH = OUTPUT_DIR / "reminder.md"

EMPTY = "--"


def load_plans(output_dir: Path = OUTPUT_DIR) -> dict:
    """读 output/plan-*.json -> {子任务 id: 记录}。"""
    plans = {}
    for path in sorted(output_dir.glob("plan-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            plans[record["day"]] = record
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            print(f"warning: 跳过无法读取的 {path.name}: {exc}", file=sys.stderr)
    return plans


def long_date(value: date | str | None) -> str:
    """date 或 '2026-10-12' -> 'Monday, October 12, 2026'。"""
    if not value:
        return EMPTY
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%A, %B %d, %Y")


def week_dates(week: dict) -> str:
    """'Tue Oct 06 - Mon Oct 12, 2026'。"""
    start, end = week["dates_start"], week["dates_end"]
    if not start or not end:
        return EMPTY
    return f"{start:%a %b %d} - {end:%a %b %d, %Y}"


def _cell(text: str) -> str:
    """转义表格单元格：竖线要转义，换行变 <br>。"""
    return text.replace("|", "\\|").replace("\n", "<br>").strip()


def _numbered(items: list[str]) -> str:
    """把一串短句排成 1. / 2. / 3. 的单元格。"""
    kept = [_cell(item) for item in items if item and item.strip()]
    if not kept:
        return EMPTY
    return "<br>".join(f"{n}. {item}" for n, item in enumerate(kept, 1))


def _planned_cell(record: dict | None) -> str:
    """该子任务生成出来的 4 个 30 分钟任务名。"""
    if not record:
        return EMPTY
    return _numbered([task.get("name", "") for task in record["plan"].get("tasks", [])])


def _deliverables_cell(record: dict | None) -> str:
    """每个任务对应的具体产出。"""
    if not record:
        return EMPTY
    return _numbered([task.get("output", "") for task in record["plan"].get("tasks", [])])


def _reminder_row(week: dict, planned: int, total: int) -> str:
    """表格最后一行的提醒。"""
    if total and planned == total:
        action = f"All {total} sub-tasks planned -- finish the deliverable and submit your study log."
    elif planned:
        action = f"Submit your study log ({planned} of {total} sub-tasks planned so far)."
    else:
        action = f"Submit your study log ({total} sub-tasks still to plan)."
    return f"| :alarm_clock: | **REMINDER** | {action} | Due **{long_date(week['deadline'])}**. |"


def week_table(week: dict, plans: dict) -> list:
    """一周 = 一张表，最后一行是提醒。"""
    tasks = week["tasks"]
    planned = sum(1 for task in tasks if task["day"] in plans)

    lines = [
        f"## Week {week['week']} -- {week['focus']}",
        "",
        f"`{week_dates(week)}` | **Deliverable:** {_cell(week['deliverable']) or EMPTY}",
        "",
        "| Sub-task | Task | Planned tasks | Deliverables |",
        "| --- | --- | --- | --- |",
    ]
    for task in tasks:
        record = plans.get(task["day"])
        lines.append(
            f"| {task['day']} | {_cell(task['task'])} "
            f"| {_planned_cell(record)} | {_deliverables_cell(record)} |"
        )
    lines.append(_reminder_row(week, planned, len(tasks)))
    lines.append("")
    return lines


def build_report(weeks: dict, plans: dict, only_week: int | None = None) -> str:
    """整份报告：每周一张表，按周排序。"""
    total = sum(len(week["tasks"]) for week in weeks.values())
    lines = [
        "# Study reminder",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} from `{DATA_PATH.name}` -- "
        f"{len(plans)} of {total} sub-tasks have a generated plan.",
        "",
    ]
    for number in sorted(weeks):
        if only_week is not None and number != only_week:
            continue
        lines.extend(week_table(weeks[number], plans))
    return "\n".join(lines).rstrip() + "\n"


def write_report(path: Path = REPORT_PATH) -> Path:
    """把整份报告（全部 16 周）写入 output/reminder.md，返回路径。"""
    text = build_report(parse_plan(DATA_PATH), load_plans())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="汇总学习计划，每周一张表。")
    parser.add_argument("--week", type=int,
                        help="只在终端显示这一周（1-16）；写进文件里的仍是全部 16 周")
    args = parser.parse_args(argv)

    weeks = parse_plan(DATA_PATH)
    if args.week is not None and args.week not in weeks:
        parser.error(f"--week 必须是 1-{max(weeks)}，收到 {args.week}")

    path = write_report()
    print(f"[report] {path}", file=sys.stderr)
    print(build_report(weeks, load_plans(), args.week), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
