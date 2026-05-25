from __future__ import annotations

from pathlib import Path

from text2sql_evolver.judge import JudgeResult, judge_sql


class ExecutionJudge:
    def evaluate(self, database_path: Path, predicted_sql: str, gold_sql: str) -> JudgeResult:
        return judge_sql(database_path, predicted_sql, gold_sql)
