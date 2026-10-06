"""main.py -- 入口：生成今天的学习计划，并显示本周的提醒表。

    python main.py                  # 生成今天的学习计划 + 显示本周的表
    python main.py --all-weeks      # 生成计划 + 显示全部 16 周
    python main.py --reminder       # 不调用 API，只看提醒表
    python main.py --day 3.2        # 指定子任务
    python main.py --date 2026-10-20

API key 放在 .env 的 OPENAI_API_KEY 里。
"""

import argparse
import sys
from datetime import date

import Agent
import reminder
from model_input import DATA_PATH, parse_plan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="生成今天的学习计划，并把所有计划汇总成每周一张表。",
    )
    parser.add_argument("--day", help="指定子任务 id，例如 3.2（默认：本周下一个未计划的）")
    parser.add_argument("--date", type=date.fromisoformat,
                        help="把这一天当作今天，YYYY-MM-DD（默认：今天）")
    parser.add_argument("--model", help="覆盖 .env 里的 MODEL_NAME")
    parser.add_argument("--no-save", action="store_true", help="只打印计划，不写 output/")
    parser.add_argument("--reminder", action="store_true", help="不生成计划，只显示提醒表")
    parser.add_argument("--week", type=int, help="显示第几周的表（默认：当前周）")
    parser.add_argument("--all-weeks", action="store_true", help="显示全部 16 周的表")
    args = parser.parse_args(argv)

    today = args.date or date.today()
    weeks = parse_plan(DATA_PATH)

    if args.week is not None and args.week not in weeks:
        parser.error(f"--week 必须是 1-{max(weeks)}，收到 {args.week}")

    # 1) 生成计划：Agent.py 会把结果存进 output/plan-<子任务>.json
    if not args.reminder:
        forwarded = []
        if args.day:
            forwarded += ["--day", args.day]
        if args.date:
            forwarded += ["--date", args.date.isoformat()]
        if args.model:
            forwarded += ["--model", args.model]
        if args.no_save:
            forwarded.append("--no-save")

        code = Agent.main(forwarded)
        if code != 0 or args.no_save:
            return code

    # 2) 显示提醒表：文件里始终是全部 16 周，终端只显示选中的那一周
    week_number = None if args.all_weeks else (args.week or Agent.week_for(weeks, today)["week"])
    path = reminder.write_report()
    print(f"[report] {path}", file=sys.stderr)
    print(reminder.build_report(weeks, reminder.load_plans(), week_number), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
