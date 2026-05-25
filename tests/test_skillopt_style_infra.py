from text2sql_evolver.editors.patch_budget import PatchBudget
from text2sql_evolver.editors.patch_aggregator import SQLAwarePatchAggregator
from text2sql_evolver.memory.rejected_patches import RejectedPatchStore
from text2sql_evolver.memory.skill_versions import SkillVersionManager
from text2sql_evolver.skill_manager import _candidate_patch_quality_issues, render_skill_with_patch


def test_patch_budget_limits_learned_rules():
    patch = """## Learned Rules From Validation Failures

These rules were generated from execution-based validation failures.
- **ordering_limit** (3 failures): Use LIMIT for top questions.
  - Detector evidence: missing LIMIT
- **join_path** (2 failures): Trace joins.
  - Detector evidence: missing join
- **aggregation** (1 failures): Group non-aggregates.
"""

    clipped, report = PatchBudget(max_rules=2).clip(patch)

    assert report["original_rules"] == 3
    assert report["kept_rules"] == 2
    assert report["clipped"]
    assert "**aggregation**" not in clipped
    assert "missing join" in clipped


def test_patch_aggregator_merges_same_category_without_dropping_evidence():
    bundle = SQLAwarePatchAggregator().build_bundle(
        [
            {
                "patch_id": "ordering_limit_candidate_001",
                "category": "ordering_limit",
                "rule_text": "Use LIMIT for ranking questions.",
                "support_examples": ["ex1"],
                "detector_evidence": ["missing LIMIT"],
                "contrastive_signals": ["gold has LIMIT"],
            },
            {
                "patch_id": "ordering_limit_candidate_002",
                "category": "ordering_limit",
                "rule_text": "Use explicit ORDER BY direction for top or bottom questions.",
                "support_examples": ["ex2"],
                "detector_evidence": ["wrong ORDER BY direction"],
                "contrastive_signals": ["successful query orders descending"],
            },
        ]
    )

    assert len(bundle.candidate_patches) == 2
    assert len(bundle.aggregated_patches) == 1
    aggregated = bundle.aggregated_patches[0]
    assert aggregated["category"] == "ordering_limit"
    assert aggregated["merged_from"] == ["ordering_limit_candidate_001", "ordering_limit_candidate_002"]
    assert aggregated["support_examples"] == ["ex1", "ex2"]
    assert aggregated["detector_evidence"] == ["missing LIMIT", "wrong ORDER BY direction"]
    assert "Use LIMIT" in aggregated["rule_text"]
    assert "ORDER BY" in aggregated["rule_text"]
    assert "Merged from" in bundle.markdown


def test_candidate_patch_quality_flags_truncated_ungrounded_rule():
    issues = _candidate_patch_quality_issues(
        [
            {
                "patch_id": "ordering_limit_candidate_001",
                "category": "ordering_limit",
                "rule_text": "When a question asks for a single entity with the",
                "support_examples": [],
                "detector_evidence": [],
            }
        ]
    )

    assert "ordering_limit_candidate_001: rule_text_looks_incomplete" in issues
    assert "ordering_limit_candidate_001: missing_support_and_evidence" in issues


def test_render_skill_with_patch_replaces_previous_learned_rules():
    original = """# Query Skill

Base instruction.

## Quality Guidelines

- guideline

## Learned Rules From Validation Failures

- old rule
"""
    patch = "## Learned Rules From Validation Failures\n\n- **value_grounding**: Match literal values to the stored format.\n"

    rendered = render_skill_with_patch(original, patch)

    assert "Base instruction." in rendered
    assert "## Mandatory Pre-SQL Plan" in rendered
    assert "Before Writing WHERE Literals" in rendered
    assert "Match literal values to the stored format." in rendered
    assert "old rule" not in rendered


def test_skill_versions_and_rejected_store(tmp_path):
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text("# Skill\n", encoding="utf-8")
    manager = SkillVersionManager(skill_path)

    record = manager.save_version(skill_text="# Skill\n\nRule\n", action="accepted", score=0.5)
    best_path = manager.promote_best("# Skill\n\nRule\n", {"score": 0.5})

    assert record.version == 1
    assert record.skill_path.exists()
    assert best_path.exists()

    store = RejectedPatchStore()
    store.add(run_id="round-1", patch_text="- bad rule", reason="validation_failed")
    path = tmp_path / "rejected.jsonl"
    store.write_jsonl(path)

    loaded = RejectedPatchStore.load(path)
    assert loaded.rows[0]["reason"] == "validation_failed"
