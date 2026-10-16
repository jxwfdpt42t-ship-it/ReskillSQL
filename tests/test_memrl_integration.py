from dataclasses import replace
import json
import sqlite3

import pytest

from text2sql_evolver.config import Settings
from text2sql_evolver.dataset import Example
from text2sql_evolver.memory.memrl import MemRLMemory, database_scope, task_key
from text2sql_evolver.runners.llm_runner import LLMRunner


class Embedder:
    def embed(self, texts):
        return [[0.0, 1.0] if "unrelated" in t else [1.0, 0.0] for t in texts]


@pytest.fixture
def settings(tmp_path):
    db = tmp_path / "source.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("CREATE TABLE people (name TEXT); INSERT INTO people VALUES ('Ann'), ('Bob');")
    skill = tmp_path / "SKILL.md"
    skill.write_text("# SQL skill\nUse only requested columns.\n")
    return Settings(tmp_path, db, tmp_path / "update.jsonl", tmp_path / "reports",
                    "fake-model", "unused", "", skill, memory_mode="learn",
                    memory_embedding_model="fake-embedding", memory_build="trajectory")


def remember(memory, *, intent="list people", outcome="failed", role="update", source="old.jsonl"):
    scope = database_scope(memory.settings.database_path)
    return memory.remember(intent=intent, evidence={"sql": "SELECT missing FROM people", "result": outcome},
        scope=scope, role=role, dataset=source, source_keys=[task_key(intent, scope)], run_id="previous",
        kind="sql_episode", outcome=outcome, skill_text="old skill")


def retrieve(memory, question="list names", skill="current", consumer="inference", **kwargs):
    return memory.retrieve(question, scope=database_scope(memory.settings.database_path),
                           consumer=consumer, skill_text=skill, **kwargs)


def test_failure_memory_can_gain_utility_and_persists(settings):
    memory = MemRLMemory(settings, embedder=Embedder())
    failed_id = remember(memory)
    success_id = remember(memory, intent="show people", outcome="direct_success")
    assert failed_id != success_id
    selected = [m for m in retrieve(memory) if m["memory_id"] == failed_id]
    q = memory.feedback(selected, reward=1.0, event_id="task1", role="update", dataset="update.jsonl")
    assert q[failed_id] == pytest.approx(0.1)
    assert memory.feedback(selected, reward=1.0, event_id="task1", role="update", dataset="update.jsonl") == {}
    reopened = MemRLMemory(settings, embedder=Embedder())
    assert retrieve(reopened)[0]["memory_id"] == failed_id
    assert retrieve(reopened)[0]["q_value"] == pytest.approx(0.1)
    assert retrieve(reopened, skill="different")[0]["q_value"] == 0
    assert retrieve(reopened, consumer="optimizer")[0]["q_value"] == 0
    assert not retrieve(reopened, question="unrelated subject")


def test_provenance_scope_and_read_only(settings):
    memory = MemRLMemory(settings, embedder=Embedder())
    mid = remember(memory)
    with pytest.raises(ValueError):
        remember(memory, role="holdout")
    with pytest.raises(ValueError):
        remember(memory, source="data/final_holdout.jsonl")
    scope = database_scope(settings.database_path)
    assert not retrieve(memory, exclude_keys=[task_key("list people", scope)])
    with memory.evaluation_scope([task_key("list people", scope)], "baseline"):
        assert not retrieve(memory)
    assert retrieve(memory)
    read = MemRLMemory(replace(settings, memory_mode="read"), embedder=Embedder())
    assert remember(read) is None
    assert read.feedback(retrieve(read), reward=1, event_id="x", role="update", dataset="x") == {}
    assert len(read.store.rows()) == 1
    assert read.store.has(mid)
    with sqlite3.connect(settings.database_path) as db:
        db.execute("ALTER TABLE people ADD COLUMN city TEXT")
    assert not retrieve(memory)  # old schema evidence is not silently reused


def test_summary_failure_keeps_observed_failure_evidence(settings):
    class BrokenSummary:
        def generate_script(self, trajectory):
            raise RuntimeError("offline")
    memory = MemRLMemory(replace(settings, memory_build="proceduralization"),
                         embedder=Embedder(), summary_provider=BrokenSummary())
    remember(memory)
    row = memory.store.rows()[0]
    assert row["metadata"]["summary_status"] == "fallback"
    assert "failed" in row["content"]
    assert row["metadata"]["evidence"]["sql"] == "SELECT missing FROM people"


def test_attempts_include_actual_error_and_learned_rule_reaches_prompt(settings, monkeypatch):
    settings.query_skill_path.write_text("## Mandatory Pre-SQL Plan\n- CHECK_CUSTOM_RULE_123\n")
    prompts = []
    def completion(settings, system, user, max_tokens):
        prompts.append(user)
        return "SELECT missing FROM people" if len(prompts) == 1 else "SELECT name FROM people"
    monkeypatch.setattr("text2sql_evolver.inner_runner.complete_text", completion)
    runner = LLMRunner(settings)
    sql = runner.generate(Example("q", "list names", "SELECT name FROM people", ()), settings.database_path)
    assert "name" in sql
    attempts = runner.execution_details()["attempts"]
    assert [a["execution_ok"] for a in attempts] == [False, True]
    assert "no such column" in prompts[1]
    assert "CHECK_CUSTOM_RULE_123" in prompts[0]
    assert all(a["correct"] is None for a in attempts)  # execution != correctness


def test_retrieved_failed_memory_is_injected_without_current_answer(settings, monkeypatch):
    memory = MemRLMemory(settings, embedder=Embedder())
    mid = remember(memory)
    def completion(settings, system, user, max_tokens):
        assert mid in user
        assert "failed" in user
        assert "CURRENT_GOLD_SENTINEL" not in user
        return "SELECT name FROM people"
    monkeypatch.setattr("text2sql_evolver.inner_runner.complete_text", completion)
    runner = LLMRunner(settings, memory=memory)
    runner.generate(Example("new", "list names", "CURRENT_GOLD_SENTINEL", ()), settings.database_path)
    assert runner.execution_details()["retrieved_memories"][0]["memory_id"] == mid


def build_orchestrator(settings, memory, monkeypatch, *, crash=False, repair=False):
    from text2sql_evolver.core.orchestrator import EvolutionOrchestrator
    from text2sql_evolver.analyzers.sql_specialized import SQLSpecializedAnalyzer
    from text2sql_evolver.editors.patch_generator import SkillPatchGenerator
    from text2sql_evolver.editors.patch_aggregator import PatchBundle
    from text2sql_evolver.runners.base import SQLRunner

    class Runner(SQLRunner):
        def generate(self, example, database_path):
            candidate = "CANDIDATE" in settings.query_skill_path.read_text()
            if candidate and crash:
                raise RuntimeError("validation interrupted")
            if example.id == "v1":
                return "SELECT name FROM people" if candidate else "SELECT 1 FROM people"
            if example.id in {"v2", "v3"}:
                return "SELECT 1 FROM people" if candidate else "SELECT name FROM people"
            return "SELECT name FROM people" if repair else "SELECT 1 FROM people"

        def execution_details(self):
            if not repair:
                return super().execution_details()
            return {"attempts": [
                {"sql": "SELECT missing FROM people", "stage": "generation", "execution_ok": False},
                {"sql": "SELECT name FROM people", "stage": "repair", "execution_ok": True}],
                "retrieved_memories": []}

    class Patcher(SkillPatchGenerator):
        def generate_bundle(self, store, *, evidence_packet=None):
            return PatchBundle([], [], "- CANDIDATE: inspect answer columns.\n")

    def routes(*args, **kwargs):
        return {"category_routes": [{"category": "projection", "fix_route": "query_skill",
                                      "confidence": 1.0, "reason": "fixture"}]}
    monkeypatch.setattr("text2sql_evolver.core.orchestrator.diagnose_fix_routes", routes)
    return EvolutionOrchestrator(settings, Runner(), SQLSpecializedAnalyzer(),
                                 patch_generator=Patcher(settings), memory=memory)


def test_rejected_skill_keeps_local_improvement_and_counterexamples(settings, monkeypatch):
    memory = MemRLMemory(settings, embedder=Embedder())
    historical = remember(memory, intent="prior naming task")
    orchestrator = build_orchestrator(settings, memory, monkeypatch)
    original = settings.query_skill_path.read_text()
    example = Example("u", "list all people names", "SELECT name FROM people", ())
    validation = [Example(f"v{i}", f"show names variant {i}", "SELECT name FROM people", ()) for i in (1, 2, 3)]
    result = orchestrator.run([example], "update.jsonl", validation_examples=validation,
                              validation_dataset_path="validation.jsonl", auto_apply=True)
    assert settings.query_skill_path.read_text() == original
    assert historical in result.summary["memory"]["optimizer_memory_ids"]
    rows = memory.store.rows()
    outcomes = {r["metadata"]["outcome"] for r in rows}
    assert {"candidate_improved_case", "candidate_regressed_case", "rejected_by_validation"} <= outcomes
    improved = next(r for r in rows if r["metadata"]["outcome"] == "candidate_improved_case")
    assert not improved["metadata"]["evidence"]["skill_promoted"]
    # Later DIFFERENT task can retrieve evidence from a rejected candidate.
    assert retrieve(memory, question="a future task")
    # The validation question cannot retrieve memories derived from its own gold feedback.
    scope = database_scope(settings.database_path)
    hits = retrieve(memory, exclude_keys=[task_key(validation[0].question, scope)])
    assert all(m["memory_id"] != improved["id"] for m in hits)
    old = next(r for r in rows if r["id"] == historical)
    assert any(q["q_value"] == pytest.approx(-0.1) for q in old["metadata"]["utilities"].values())


def test_validation_exception_restores_skill(settings, monkeypatch):
    orchestrator = build_orchestrator(settings, None, monkeypatch, crash=True)
    original = settings.query_skill_path.read_text()
    example = Example("u", "names", "SELECT name FROM people", ())
    with pytest.raises(RuntimeError, match="validation interrupted"):
        orchestrator.run([example], "update.jsonl", validation_examples=[replace(example, id="v1")],
                         validation_dataset_path="validation.jsonl")
    assert settings.query_skill_path.read_text() == original


def test_repaired_success_is_reported_from_attempts(settings, monkeypatch):
    memory = MemRLMemory(settings, embedder=Embedder())
    orchestrator = build_orchestrator(settings, memory, monkeypatch, repair=True)
    example = Example("u", "names", "SELECT name FROM people", ())
    result = orchestrator.run([example], "update.jsonl")
    assert result.examples[0].outcome == "repaired_success"
    assert result.examples[0].attempts[0]["category"] == "schema_linking"
    assert result.behavior_signals[0]["signal_type"] == "repair_heavy_success"
    assert memory.store.rows()[0]["metadata"]["outcome"] == "repaired_success"


def test_no_learning_from_holdout_before_any_model_call(settings, monkeypatch):
    memory = MemRLMemory(settings, embedder=Embedder())
    orchestrator = build_orchestrator(settings, memory, monkeypatch)
    example = Example("u", "names", "SELECT name FROM people", ())
    with pytest.raises(ValueError, match="never holdout"):
        orchestrator.run([example], "holdout.jsonl")
    with pytest.raises(ValueError, match="never holdout"):
        orchestrator.run([example], "update.jsonl", validation_examples=[example],
                         validation_dataset_path="final_test.jsonl")
    assert memory.store.rows() == []


def test_same_source_id_excluded_even_after_question_rewrite(settings):
    from text2sql_evolver.memory.memrl import source_keys
    memory = MemRLMemory(settings, embedder=Embedder())
    scope = database_scope(settings.database_path)
    memory.remember(intent="old wording", evidence={"result": "success"}, scope=scope,
        role="update", dataset="update.jsonl", source_keys=source_keys("old wording", scope, "derived1", "original1"),
        run_id="r", kind="sql_episode", outcome="direct_success", skill_text="old")
    assert not retrieve(memory, exclude_keys=source_keys("new wording", scope, "derived2", "original1"))


def test_feedback_transaction_rolls_back_partial_updates(settings):
    memory = MemRLMemory(settings, embedder=Embedder())
    remember(memory)
    selected = retrieve(memory)
    with pytest.raises(RuntimeError, match="Unable to fetch"):
        memory.feedback(selected + [{**selected[0], "memory_id": "zz-missing"}], reward=1,
                        event_id="broken", role="update", dataset="update.jsonl")
    assert memory.store.rows()[0]["metadata"]["utilities"] == {}
    with memory.store.connect() as db:
        assert db.execute("SELECT count(*) FROM feedback").fetchone()[0] == 0


def test_live_comparison_reads_frozen_bank_without_learning(settings, monkeypatch):
    from text2sql_evolver.benchmarks.live_skill_compare import compare_live_skills
    memory = MemRLMemory(settings, embedder=Embedder())
    remember(memory)
    readonly = MemRLMemory(replace(settings, memory_mode="read"), embedder=Embedder())
    before = memory.store.path.read_bytes()
    monkeypatch.setattr("text2sql_evolver.benchmarks.live_skill_compare.make_memory", lambda s: readonly)
    calls = []
    def completion(settings, system, user, max_tokens):
        calls.append(user)
        assert "Historical experiences" in user
        return "SELECT name FROM people"
    monkeypatch.setattr("text2sql_evolver.inner_runner.complete_text", completion)
    dataset = settings.project_root / "holdout.jsonl"
    dataset.write_text(json.dumps({"id": "new", "question": "list names", "gold_sql": "SELECT name FROM people"}) + "\n")
    after_skill = settings.project_root / "candidate.md"
    after_skill.write_text("New instruction")
    result = compare_live_skills(settings=settings, dataset_path=dataset,
        before_skill=settings.query_skill_path, after_skill=after_skill)
    assert result["before_correct"] == result["after_correct"] == 1
    assert len(calls) == 2
    assert memory.store.path.read_bytes() == before
