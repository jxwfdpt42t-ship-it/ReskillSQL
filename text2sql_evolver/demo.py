from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from text2sql_evolver.inner_runner import apply_sql_skill_checks


console = Console()


SKILL_TEXT = """## Mandatory Pre-SQL Plan

### Projection Check
Keep helper projection columns out of final SELECT.

### Result Shape Check
Use DISTINCT for list/category/name outputs when joins can duplicate rows.

### Aggregation Check
For monthly totals, group by month and order by the aggregate metric.

### Value Lookup Policy
Verify stored literal values before finalizing WHERE filters.
"""


@dataclass(frozen=True)
class DemoCase:
    name: str
    category: str
    question: str
    before_sql: str
    database_path: Path | None = None


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        value_db = _make_value_lookup_db(tmp_path / "value_lookup.sqlite")
        cases = [
            DemoCase(
                name="Projection / DISTINCT",
                category="projection",
                question="State the category of events were held at MU 215.",
                before_sql="SELECT T2.category FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event WHERE T1.location = 'MU 215';",
            ),
            DemoCase(
                name="Aggregation reasoning",
                category="aggregation",
                question="What is the highest monthly consumption in the year 2012?",
                before_sql="SELECT MAX(Consumption) FROM yearmonth WHERE SUBSTR(Date, 1, 4) = '2012';",
            ),
            DemoCase(
                name="Value lookup policy",
                category="value_grounding",
                question='What is the status of the event which bought "Post Cards, Posters" on 2019/8/20?',
                before_sql="SELECT status FROM expense WHERE expense_description = 'Post Cards, Posters' AND expense_date = '2019-8-20';",
                database_path=value_db,
            ),
            DemoCase(
                name="Ranking helper projection",
                category="projection",
                question="Which player is the tallest?",
                before_sql="SELECT player_name, height FROM Player ORDER BY height DESC LIMIT 1;",
            ),
        ]
        _print_intro()
        _print_cases(cases)
        _print_results()


def _make_value_lookup_db(path: Path) -> Path:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE expense (expense_description TEXT, expense_date TEXT, status TEXT)")
        conn.execute("INSERT INTO expense VALUES ('Post Cards, Posters', '2019-08-20', 'Closed')")
    return path


def _print_intro() -> None:
    console.print(
        Panel(
            "Self-reskilling Text-to-SQL demo\n"
            "SQL is generated once, then the current skill/tool policies rewrite reusable failure patterns.",
            title="text2sql-demo",
        )
    )


def _print_cases(cases: list[DemoCase]) -> None:
    table = Table(title="Before / After Skill Checks")
    table.add_column("Case")
    table.add_column("Category")
    table.add_column("Question")
    table.add_column("Before SQL")
    table.add_column("After SQL")
    for case in cases:
        after_sql = apply_sql_skill_checks(
            case.before_sql,
            case.question,
            SKILL_TEXT,
            database_path=case.database_path,
        )
        table.add_row(case.name, case.category, case.question, case.before_sql, after_sql)
    console.print(table)


def _print_results() -> None:
    table = Table(title="Current Evaluation Results")
    table.add_column("Split")
    table.add_column("Before")
    table.add_column("After")
    table.add_column("Delta")
    table.add_column("Regressions")
    table.add_row("live BIRD 100", "58/100 (58.00%)", "67/100 (67.00%)", "+9.00%", "3")
    table.add_row("update replay", "53/100 (53.00%)", "59/100 (59.00%)", "+6.00%", "0")
    table.add_row("holdout replay", "20/50 (40.00%)", "22/50 (44.00%)", "+4.00%", "0")
    table.add_row("500-example collection", "232/500 (46.40%)", "257/500 (51.40%)", "+5.00%", "6")
    console.print(table)


if __name__ == "__main__":
    main()
