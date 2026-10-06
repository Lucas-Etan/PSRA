from pathlib import Path
from datetime import date
import re
import json


DATA_PATH = Path("/mnt/data/Python/PSRA/learning_project.txt")

# 1-16 周，每周 1-6 个子任务
SUBTASK_RE = re.compile(r"^\s+(\d{1,2}\.\d)\s+(.+?)\s+\([\d.]+\s*h\)\s*$")

# 每周的日期区间与截止日期
DATES_RE = re.compile(r"^Dates\s*\.*\s*(.+)$")
DEADLINE_RE = re.compile(r"^Deadline\s*\.*\s*(.+)$")

WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _to_date(text: str, year: int | None = None) -> date | None:
    """把 'Tue Oct 06' / 'Monday, October 12, 2026' 解析成 date。

    日期区间的左端不带年份，用 year 参数补上。
    """
    parts = text.replace(",", " ").split()

    for i, part in enumerate(parts):
        if len(part) == 4 and part.isdigit():
            year = int(parts.pop(i))
            break

    if parts and parts[0][:3].lower() in WEEKDAYS:
        parts.pop(0)

    if year is None or len(parts) < 2 or not parts[1].isdigit():
        return None

    month = MONTHS.get(parts[0][:3].lower())
    if month is None:
        return None
    return date(year, month, int(parts[1]))


def parse_plan(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    weeks = {}
    current_week = None
    pending_section = None  # 'topic' or 'deliverable'

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 匹配 WEEK N -- Focus
        m = re.match(r"^WEEK\s+(\d{1,2})\s+--\s+(.+)$", stripped)
        if m:
            week_num = int(m.group(1))
            current_week = {
                "week": week_num,
                "focus": m.group(2).strip(),
                "topic": "",
                "deliverable": "",
                "tasks": [],
                "dates_start": None,
                "dates_end": None,
                "deadline": None,
            }
            weeks[week_num] = current_week
            pending_section = None
            continue

        if current_week is None:
            continue

        # 匹配日期区间 Dates ... Tue Oct 06 - Mon Oct 12, 2026
        m = DATES_RE.match(stripped)
        if m:
            left, _, right = m.group(1).partition("-")
            dates_end = _to_date(right)
            dates_start = _to_date(left, year=dates_end.year if dates_end else None)
            # 跨年的周（Dec 29 - Jan 04）左端属于上一年
            if dates_start and dates_end and dates_start > dates_end:
                dates_start = dates_start.replace(year=dates_start.year - 1)
            current_week["dates_start"] = dates_start
            current_week["dates_end"] = dates_end
            continue

        # 匹配截止日期 Deadline ... Monday, October 12, 2026
        m = DEADLINE_RE.match(stripped)
        if m:
            current_week["deadline"] = _to_date(m.group(1))
            continue

        # 标记：下一非空行是 topic
        if stripped == "Topic":
            pending_section = "topic"
            continue

        # 标记：下一非空行是 deliverable
        if stripped == "Deliverable":
            pending_section = "deliverable"
            continue

        # 匹配子任务 1-16 . 1-6
        m = SUBTASK_RE.match(line)
        if m:
            current_week["tasks"].append({
                "day": m.group(1),
                "task": m.group(2).strip(),
            })
            pending_section = None
            continue

        # 收集 topic / deliverable 的正文：会换行，缩进行继续追加
        if pending_section:
            if stripped and line[:1].isspace():
                current_week[pending_section] = " ".join(
                    filter(None, (current_week[pending_section], stripped))
                )
                continue
            pending_section = None  # 空行或下一节标题，结束收集

    return weeks


def build_expected_input(week: dict) -> dict:
    return {
        "topic": week["topic"],
        "deliverable": week["deliverable"],
        "tasks": week["tasks"],
    }


if __name__ == "__main__":
    weeks = parse_plan(DATA_PATH)
    result = build_expected_input(weeks[3])
    print(json.dumps(result, ensure_ascii=False, indent=2))