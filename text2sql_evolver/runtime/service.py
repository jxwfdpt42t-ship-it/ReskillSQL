"""Trusted administration, input freezing and the actual query/evolution adapters."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import fcntl
import json
import math
from pathlib import Path
import re
import shutil

from text2sql_evolver.config import Settings
from text2sql_evolver.dataset import Example, load_jsonl
from text2sql_evolver.memory.experience_store import ExperienceStore
from .artifacts import Releases, checksum, snapshot_sqlite, write_json, write_text
from .store import ControlStore, Conflict, encode


PROFILE_FIELDS = ("model_name", "base_url", "memory_embedding_model", "memory_embedding_base_url",
                  "memory_build", "memory_inference", "memory_alpha", "memory_similarity_threshold",
                  "memory_candidates", "memory_top_k", "memory_context_chars")


def json_cell(cell):
    if isinstance(cell, bytes):
        return {"hex": cell.hex()}
    if isinstance(cell, float) and not math.isfinite(cell):
        return {"float": str(cell)}
    return cell


class Runtime:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.store = ControlStore(self.root)
        self.releases = Releases(self.root)

    def initialize(self, settings: Settings, databases: dict, *, memory=False):
        with (self.root / "initialize.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            return self._initialize(settings, databases, memory=memory)

    def _initialize(self, settings, databases, *, memory):
        if (self.root / "config.json").exists():
            raise Conflict("Use a new empty runtime directory for initialization")
        if not databases:
            raise ValueError("At least one database is required")
        if memory and not settings.memory_embedding_model:
            raise ValueError("Memory requires TEXT2SQL_MEMORY_EMBEDDING_MODEL")
        registry = {}
        for name, source in databases.items():
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
                raise ValueError("Invalid database alias")
            target = self.root / "databases" / (name + ".sqlite")
            snapshot_sqlite(source, target)
            target.chmod(0o400)
            registry[name] = {"path": str(target), "sha256": checksum(target)}
        empty = self.root / "bootstrap" / "memory.sqlite"
        ExperienceStore(empty)
        profile = {field: getattr(settings, field) for field in PROFILE_FIELDS}
        profile["memory_enabled"] = memory
        manifest = self.releases.build(settings.query_skill_path, empty, profile=profile, parent_revision=0)
        write_json(self.root / "config.json", {"databases": registry})
        self.store.initialize(manifest)
        return self.store.current()

    def databases(self):
        return json.loads((self.root / "config.json").read_text())["databases"]

    def submit_query(self, database, question, evidence, key):
        if database not in self.databases():
            raise ValueError("Unknown database alias")
        if not isinstance(question, str) or not question.strip() or len(question) > 16000:
            raise ValueError("Question must contain 1..16000 characters")
        if evidence is not None and (not isinstance(evidence, str) or len(evidence) > 16000):
            raise ValueError("Evidence must be at most 16000 characters")
        request = {"database": database, "question": question, "evidence": evidence}
        fingerprint = hashlib.sha256(encode(request).encode()).hexdigest()
        payload = {**request, **self.store.current()}
        # A retry after publication returns the original pinned job, not a new version.
        return self.store.enqueue("query", payload, key, fingerprint=fingerprint)

    def submit_evolution(self, update, validation, release_checks, key):
        """Admin-only: registered DB aliases, verified references, immutable input files."""
        from text2sql_evolver.judge import execute_sql
        from text2sql_evolver.memory.memrl import require_learning_source
        registry = self.databases()
        all_sources, all_source_ids, all_questions, datasets = set(), set(), set(), {}
        for role, path in (("update", update), ("validation", validation), ("release_checks", release_checks)):
            require_learning_source("validation" if role == "release_checks" else role, str(path))
            rows = []
            ids = set()
            for raw in Path(path).read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                row = json.loads(raw)
                if row.get("split") in {"holdout", "test"} or row.get("dataset_role") in {"holdout", "test"}:
                    raise ValueError("Final holdout cannot select a production release")
                if not isinstance(row.get("question"), str) or not row["question"].strip():
                    raise ValueError("Question must be nonempty")
                alias = row.get("db_id")
                if alias not in registry or not row.get("source_id") or not row.get("id"):
                    raise ValueError("Every task needs a registered db_id, id and stable source_id")
                source = (alias, str(row.get("source_family") or row["source_id"]))
                original_source = (alias, str(row["source_id"]))
                question = (alias, " ".join(row["question"].lower().split()))
                if source in all_sources or original_source in all_source_ids or question in all_questions or str(row["id"]) in ids:
                    raise ValueError("Duplicate/source-overlapping tasks; use independent source families")
                all_sources.add(source)
                all_source_ids.add(original_source)
                all_questions.add(question)
                ids.add(str(row["id"]))
                db_path = registry[alias]["path"]
                if not execute_sql(Path(db_path), row["gold_sql"]).ok:
                    raise ValueError("Reference SQL must execute on the registered snapshot")
                # Ignore arbitrary caller-supplied paths; only registered snapshots may execute.
                rows.append({"id": str(row["id"]), "source_id": str(source[1]), "db_id": alias,
                             "db_path": db_path, "question": row["question"], "gold_sql": row["gold_sql"],
                             "evidence": row.get("evidence"), "tags": row.get("tags", [])})
            if not rows or len(rows) > 10000:
                raise ValueError("Each development dataset must contain 1..10000 tasks")
            datasets[role] = rows
        fingerprint = hashlib.sha256(encode(datasets).encode()).hexdigest()
        bundle = self.root / "inputs" / fingerprint
        bundle.mkdir(parents=True, exist_ok=True)
        files = {}
        for role, rows in datasets.items():
            path = bundle / (role + ".jsonl")
            content = "".join(encode(row) + "\n" for row in rows)
            # Content-addressed input is immutable; concurrent identical submissions are harmless.
            if path.exists():
                if path.read_text(encoding="utf-8") != content:
                    raise Conflict("Input bundle is incomplete or has been modified; retry submission")
            else:
                write_text(path, content)
            files[role] = {"path": str(path), "sha256": checksum(path)}
        active = self.store.current()
        payload = {"release_id": active["release_id"], "parent_revision": active["revision"], "datasets": files}
        return self.store.enqueue("evolve", payload, key, fingerprint=fingerprint, max_attempts=2, capacity=20)

    def settings_for(self, settings, manifest, work, *, learning=False):
        release = self.releases.verify(manifest)
        profile = dict(manifest["profile"])
        enabled = profile.pop("memory_enabled")
        if learning:
            skill = work / "skills" / "query-writing" / "SKILL.md"
            skill.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(release / "SKILL.md", skill)
            memory = work / "data" / "memrl" / "experiences.sqlite"
            snapshot_sqlite(release / "memory.sqlite", memory)
        else:
            skill, memory = release / "SKILL.md", release / "memory.sqlite"
        return replace(settings, **profile, project_root=work, query_skill_path=skill,
                       reports_dir=work / "reports", memory_path=memory,
                       memory_mode=("learn" if learning else "read") if enabled else "off")

    def execute(self, job, work, settings):
        from text2sql_evolver.memory.memrl import make_memory
        from text2sql_evolver.runners.llm_runner import LLMRunner
        payload = job["payload"]
        manifest = self.store.release(payload["release_id"])
        learning = job["kind"] == "evolve"
        settings = self.settings_for(settings, manifest, work, learning=learning)
        registry = self.databases()
        # Snapshot corruption must not silently change the meaning of a pinned release.
        aliases = [payload["database"]] if not learning else registry.keys()
        for alias in aliases:
            if checksum(registry[alias]["path"]) != registry[alias]["sha256"]:
                raise ValueError("Database snapshot changed")
        if not learning:
            database = Path(registry[payload["database"]]["path"])
            example = Example(job["id"], payload["question"], "", (), evidence=payload["evidence"])
            runner = LLMRunner(settings, memory=make_memory(settings))
            sql = runner.generate(example, database)
            write_json(work / "query_trace.json", {"job_id": job["id"], "release_id": manifest["id"],
                       "database": payload["database"], "question": example.question,
                       "evidence": example.evidence, "sql": sql, **runner.execution_details()})
            from text2sql_evolver.judge import execute_sql
            result = execute_sql(database, sql, max_rows=100)
            return {"result": {"release_id": manifest["id"], "sql": sql, "execution_ok": result.ok,
                               "rows": [[json_cell(cell) for cell in row] for row in result.rows],
                               "rows_truncated": result.truncated,
                               "error": result.error,
                               "memory_ids": [m["memory_id"] for m in runner.details["retrieved_memories"]]}}
        datasets = {}
        for role, item in payload["datasets"].items():
            if checksum(item["path"]) != item["sha256"]:
                raise ValueError("Dataset snapshot changed")
            datasets[role] = load_jsonl(Path(item["path"]))
        from text2sql_evolver.analyzers.sql_specialized import SQLSpecializedAnalyzer
        from text2sql_evolver.core.orchestrator import EvolutionOrchestrator
        from text2sql_evolver.validators.sql_aware_gate import SQLAwareGate
        memory = make_memory(settings)
        result = EvolutionOrchestrator(settings, LLMRunner(settings, memory), SQLSpecializedAnalyzer(),
                                       memory=memory, gate=SQLAwareGate(allow_weak_pass=False)).run(
            datasets["update"], payload["datasets"]["update"]["path"], auto_apply=True,
            validation_examples=datasets["validation"],
            validation_dataset_path=payload["datasets"]["validation"]["path"])
        # Evaluate the FINAL Skill + learned Memory bundle, not just the pre-learning Skill.
        # release_checks is development promotion data, never final holdout and never learned.
        before_settings = self.settings_for(settings, manifest, work / "before")
        after_settings = replace(settings, memory_mode="read" if memory else "off")
        before = self.evaluate(before_settings, datasets["release_checks"])
        after = self.evaluate(after_settings, datasets["release_checks"])
        regressions = [task for task in before if before[task] and not after[task]]
        check = {"before_correct": sum(before.values()), "after_correct": sum(after.values()),
                 "total": len(before), "regressions": regressions}
        write_json(work / "release_check.json", check)
        outcome = {"published": False, "report": str(result.run_dir), "release_check": check}
        if regressions or sum(after.values()) < sum(before.values()):
            return {"result": {**outcome, "reason": "bundle_validation_rejected"}}
        proposed = self.releases.build(settings.query_skill_path, settings.memory_path,
                                      profile=manifest["profile"], parent_revision=payload["parent_revision"],
                                      metadata={"job_id": job["id"], "release_check": check,
                                                "parent_release": manifest["id"], "datasets": payload["datasets"]})
        return {"result": outcome, "manifest": proposed}

    @staticmethod
    def evaluate(settings, examples):
        from text2sql_evolver.judge import judge_sql
        from text2sql_evolver.memory.memrl import make_memory
        from text2sql_evolver.runners.llm_runner import LLMRunner
        runner = LLMRunner(settings, make_memory(settings))
        results = {}
        for example in examples:
            database = Path(example.db_path)
            judged = judge_sql(database, runner.generate(example, database), example.gold_sql)
            if not judged.gold.ok:
                raise ValueError("Invalid reference in release checks")
            results[example.id] = judged.correct
        return results
