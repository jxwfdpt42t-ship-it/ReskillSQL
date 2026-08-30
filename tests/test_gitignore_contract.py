import subprocess


def is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", path],
        check=False,
    )
    return result.returncode == 0


def test_sensitive_and_generated_artifacts_are_ignored() -> None:
    assert is_ignored(".env")
    assert is_ignored("data/bird/raw/minidev.zip")
    assert is_ignored("reports/example.json")
    assert is_ignored(".venv/bin/python")


def test_public_report_readme_is_not_ignored() -> None:
    assert not is_ignored("reports/README.md")
