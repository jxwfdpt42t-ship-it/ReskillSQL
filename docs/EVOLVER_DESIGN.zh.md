# Evolver 设计

evolver 是围绕 Text-to-SQL agent 的外层学习闭环。它不更新模型权重，而是在观察执行轨迹之后，更新 agent 外部的 skill memory。

```text
generate SQL -> execute/judge -> diagnose SQL-specific failure -> propose skill patch -> validate -> accept or roll back
```

也就是：

```text
生成 SQL -> 执行/判分 -> 诊断 SQL 特化错误 -> 提出 skill patch -> 验证 -> 接受或回滚
```

## 核心主张

SQL 很适合做 self-evolving agent，因为它提供了：

- 可执行反馈
- 明确的 schema 约束
- 可拆解的 clause 结构
- 可以在 held-out questions 上重复验证

和开放式自然语言生成不同，SQL 的失败通常可以定位到 schema linking、join、filtering、aggregation、ordering、projection、value grounding 或 runtime error。这使得定向的 skill update 成为可能。

## SQL 特化操作

| 操作 | 作用 | 为什么适合 SQL |
|---|---|---|
| Clause-level analysis | 把 SQL 拆成 `SELECT / FROM / JOIN / WHERE / GROUP BY / ORDER BY / LIMIT`，并定位失败 clause。 | SQL 是结构化语言，所以错误通常能映射到明确 clause，而不是模糊的自由文本行为。 |
| Schema linking check | 检查 predicted tables/columns 是否存在，以及是否匹配问题意图。 | Text-to-SQL 经常因为选错表或业务列而失败，尤其是在 BIRD 这种真实业务 schema 上。 |
| Join path analysis | 检测漏 join、多 join、join path 不连通、可疑 join condition。 | 多表 SQL 依赖 schema graph 和 foreign-key path，这些可以直接检查。 |
| Value grounding check | 把问题里的实体映射到数据库真实值，并捕捉 value mismatch。 | 很多 SQL 错误不是语法错，而是 value 错，比如 `Alameda County` vs `Alameda`。 |
| Execution error classification | 分类 runtime errors，比如 no such table、no such column、ambiguous column、syntax error、timeout。 | SQL 执行错误是强反馈，而且每类错误都有自然的修复策略。 |
| Result-shape comparison | 比较行数、列数、单行聚合形状、top-k 形状、返回值类型。 | SQL 能执行不代表正确；错误 shape 可以暴露 aggregation、projection 或 `LIMIT` 缺失。 |
| Aggregation reasoning check | 检查 `COUNT/SUM/AVG/MIN/MAX`、`GROUP BY`、非聚合 select 列。 | SQL 聚合有明确规则，常见错误可以通过结构检查发现。 |
| Ratio / percentage handling | 处理 rate、percentage、average、difference、`REAL` cast、`NULLIF` denominator、按计算指标排序。 | BIRD 经常使用 evidence 定义公式，数值 SQL 容易出现整数除法和除零问题。 |
| Order / limit / tie-break check | 检查 top/bottom/latest/highest/lowest ranking semantics、`ORDER BY` 方向、`LIMIT`、稳定 tie-breaker。 | 排名类问题很常见；缺 `LIMIT` 或排序不稳定会导致 execution-equivalent intent 失败。 |
| Evidence usage check | 检查 BIRD evidence 里的公式、业务定义、filter 是否体现在 SQL 中。 | BIRD 提供 evidence 字段，所以可以做 domain-grounded diagnosis，而不是泛泛 reflection。 |
| SQL safety guard | 阻止 `INSERT/UPDATE/DELETE/DROP/ALTER/PRAGMA` 等非只读语句。 | 公开 benchmark runner 必须能安全执行模型生成的 SQL。 |
| Skill patch validation | 在 held-out examples 上验证 skill edits，并基于实际表现接受或回滚。 | 执行准确率提供了具体 acceptance signal，避免 prompt edits 变成不可控 reflection。 |

## 为什么这不只是 Reflection

普通 reflection 系统会让 LLM 总结自己哪里错了。这个 evolver 不一样：它先利用 SQL 结构产生 grounded diagnosis，然后再让 LLM 或规则生成 skill patch。

LLM 被使用之前，系统已经收集了这些证据：

```text
wrong query
gold query
execution error or mismatch
schema
clause-level diff
failure category
BIRD evidence
validation result
```

这种设计让 skill patch 更容易审计、更容易验证，也更不容易过拟合单个样例。

## 实现路径

1. 保持当前 smoke-test loop 可运行。
2. 一次实现一个 specialized detector。
3. 把每个 detector 的结果写进 `failures.json`。
4. 让 `skill_manager.py` 基于 detector evidence 生成 patch，而不只是基于 category name。
5. 在接受 skill edits 之前加入 validation/rollback。现在已经支持可选 validation split；下一步是 final holdout reporting。

## 外层架构

外层 evolver 被拆成明确的层，这样每个研究想法都有稳定的位置。

```text
text2sql_evolver/
├── core/          # state and orchestration
├── runners/       # inner Text-to-SQL execution backends
├── evaluators/    # execution judge and metrics
├── analyzers/     # SQL-specialized failure diagnosis
├── memory/        # failure stores and evolution history
├── editors/       # skill patch generation and editing
├── validators/    # acceptance, rollback, future holdout validation
├── benchmarks/    # BIRD/Spider/self-update benchmark adapters
├── reports/       # JSON and markdown report writers
└── utils/         # path, JSONL, and shared helpers
```

当前 `text2sql-evolve` 命令会经过 `core.orchestrator.EvolutionOrchestrator`：

```text
load examples
-> runner.generate()
-> execution_judge.evaluate()
-> sql_specialized_analyzer.analyze()
-> patch_generator.generate()
-> acceptance_policy.decide()
-> skill_editor.apply() when accepted
-> json/markdown reporters
```

这个设计刻意比单脚本更结构化。它允许我们替换一个弱组件，而不需要改动整条链路。例如，`analyzers/sql_specialized.py` 一开始可以是 heuristic，之后可以升级成 multi-detector SQL diagnosis engine。
