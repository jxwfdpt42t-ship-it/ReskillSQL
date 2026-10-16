"""Persist task and candidate-validation experiences after a frozen round."""
from __future__ import annotations

from .memrl import database_scope, source_keys as example_keys


def learn_round(memory, *, runs, trajectory_cards, run_id, dataset, role, old_skill,
                patch, gate_metrics, decision, before_rows, after_rows, validation_dataset,
                optimizer_memories):
    if not memory.learning:
        return []
    added = []
    routes = {str(c["example_id"]): c for c in trajectory_cards}
    source_keys = set()
    for run in runs:
        scope = database_scope(run.database_path)
        keys = example_keys(run.example.question, scope, run.example.id, run.example.source_id)
        source_keys.update(keys)
        for recalled in run.retrieved_memories:
            source_keys.update(recalled.get("source_keys", []))
        if not run.judge.gold.ok:
            continue
        evidence = run.to_report_row()
        evidence["fix_route"] = routes.get(str(run.example.id), {}).get("fix_route", "uncertain")
        memory.feedback(run.retrieved_memories, reward=1.0 if run.correct else -1.0,
                        event_id=f"{run_id}:task:{scope}:{run.example.id}", role=role, dataset=dataset)
        own_keys = set(keys)
        for recalled in run.retrieved_memories:
            own_keys.update(recalled.get("source_keys", []))
        added.append(memory.remember(intent=run.example.question, evidence=evidence,
            scope=scope, role=role, dataset=dataset, source_keys=own_keys, run_id=run_id,
            kind="sql_episode", outcome=run.outcome, skill_text=old_skill))

    if not patch or before_rows is None or after_rows is None:
        return added
    from pathlib import Path
    before_by_id = {str(row["id"]): row for row in before_rows}
    for row in before_rows:
        source_keys.update(example_keys(row["question"], database_scope(Path(row["db_path"])), row["id"], row.get("source_id")))
    for recalled in optimizer_memories:
        source_keys.update(recalled.get("source_keys", []))
    # Reward measures the tested candidate, independent of whether promotion was enabled.
    passed = (gate_metrics or {}).get("gate_level") in {"strong_pass", "weak_pass"}
    memory.feedback(optimizer_memories, reward=1.0 if passed else -1.0,
                    event_id=f"{run_id}:optimizer", role="validation", dataset=validation_dataset)
    for after in after_rows:
        before = before_by_id[str(after["id"])]
        if any(str(row["reason"]).startswith("gold_sql_failed") for row in (before, after)):
            continue
        if before["correct"] == after["correct"]:
            continue
        scope = database_scope(Path(after["db_path"]))
        outcome = "candidate_improved_case" if after["correct"] else "candidate_regressed_case"
        added.append(memory.remember(intent=after["question"], scope=scope,
            evidence={"before": before, "after": after, "candidate_patch": patch,
                      "candidate_gate": gate_metrics, "skill_promoted": decision.accepted,
                      "decision_reason": decision.reason,
                      "caution": "A local improvement does not validate the whole patch; a regression is counterevidence."},
            role="validation", dataset=validation_dataset, source_keys=source_keys, run_id=run_id,
            kind="skill_validation", outcome=outcome, skill_text=old_skill))
    # Preserve even wholly unsuccessful edits with no changed cases, by database scope.
    seen_scopes = set()
    for run in runs:
        scope = database_scope(run.database_path)
        if scope in seen_scopes:
            continue
        seen_scopes.add(scope)
        added.append(memory.remember(intent=run.example.question + " Skill update " +
            " ".join(sorted({c["category"] for c in trajectory_cards})),
            evidence={"patch": patch, "gate_metrics": gate_metrics,
                      "promoted": decision.accepted, "decision_reason": decision.reason,
                      "status": "passed_validation" if passed else "rejected_by_validation"},
            scope=scope, role="validation", dataset=validation_dataset,
            source_keys=source_keys, run_id=run_id, kind="skill_update",
            outcome="passed_validation" if passed else "rejected_by_validation", skill_text=old_skill))
    return added
