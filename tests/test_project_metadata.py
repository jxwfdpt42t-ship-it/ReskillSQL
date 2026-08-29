import tomllib
from pathlib import Path


def test_project_repository_url_points_to_public_repo() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())

    urls = pyproject["project"]["urls"]

    assert urls["Repository"] == "https://github.com/jxwfdpt42t-ship-it/ReskillSQL"
    assert urls["Issues"].endswith("/ReskillSQL/issues")
