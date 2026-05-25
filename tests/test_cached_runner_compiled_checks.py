from pathlib import Path
from types import SimpleNamespace

from text2sql_evolver.dataset import Example
from text2sql_evolver.runners.cached_runner import CachedRunner


class _Fallback:
    def __init__(self, skill_path: Path) -> None:
        self.settings = SimpleNamespace(query_skill_path=skill_path)

    def generate(self, example, database_path):  # pragma: no cover
        raise AssertionError("fallback should not be called")


def test_cached_runner_applies_projection_check(tmp_path: Path):
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text("## Mandatory Pre-SQL Plan\n\n### Projection Check\n", encoding="utf-8")
    runner = CachedRunner(
        {
            "ex": (
                "SELECT T1.molecule_id, T1.label FROM molecule AS T1 "
                "WHERE T1.label = '-' GROUP BY T1.molecule_id;"
            )
        },
        fallback=_Fallback(skill_path),
    )
    example = Example(id="ex", question="Which non-carcinogenic molecules?", gold_sql="", tags=())

    sql = runner.generate(example, Path("dummy.sqlite"))

    assert sql.startswith("SELECT T1.molecule_id FROM")
