# 系统脉络说明

这个文件从代码结构到运行流程，解释当前系统是怎么工作的。

## 运行流程

```text
CLI: text2sql-evolve
  -> run_round.py 解析命令行参数
  -> load_settings() 读取模型、数据库、报告路径等配置
  -> load_jsonl() 读取 benchmark 样例
  -> EvolutionOrchestrator.run()
      -> runner.generate() 生成 SQL
      -> execution judge 对比 predicted/gold 的执行结果
      -> SQL-specialized analyzer 诊断错误样例
      -> patch generator 起草可学习的 skill 规则
      -> 可选 validation split 测试这个 patch
      -> acceptance policy 决定接受或拒绝 patch
      -> 如果验证退化，rollback 恢复备份
      -> reporters 写出 JSON/Markdown 报告
```

## 文件与职责

### 根目录

- `agent.py`: DeepAgents baseline 的 Text-to-SQL CLI。
- `AGENTS.md`: agent 层面的常驻指令，每次运行都会加载。
- `skills/query-writing/SKILL.md`: SQL 写作 skill，也是 evolver 主要修改的文件。
- `skills/schema-exploration/SKILL.md`: schema 探索 skill。
- `pyproject.toml`: Python 包信息、依赖、CLI 命令。
- `.env.example`: 安全的环境变量模板。
- `.gitignore`: 排除密钥、报告、本地 benchmark 数据和缓存。
- `README.md`: 面向 GitHub 读者的项目入口。
- `PROJECT_PLAN.md`: milestone 和简历叙事框架。
- `FILE_GUIDE.md`: 快速文件索引。

### Data

- `data/chinook_eval.jsonl`: 本地 smoke-test benchmark。
- `data/bird/README.md`: 占位说明，告诉你官方 BIRD 数据应该放在哪里。

### 配置与数据加载

- `text2sql_evolver/config.py`: 模型、backend、路径配置；支持 Gemini 和 OpenAI-compatible endpoint。
- `text2sql_evolver/dataset.py`: JSONL 样例加载器；支持每条样例自己的 `db_path`、`db_id`、`evidence`、`difficulty`。
- `text2sql_evolver/schema.py`: 读取 SQLite schema，用于放进 prompt。

### Core

- `text2sql_evolver/core/orchestrator.py`: 最核心的外层 evolver。它把 runner、judge、analyzer、editor、validator、rollback、reporter 串起来。
- `text2sql_evolver/core/state.py`: 定义一个样例运行结果和一轮 evolution 的可报告状态对象。

### Runners

- `text2sql_evolver/runners/base.py`: runner 接口。
- `text2sql_evolver/runners/llm_runner.py`: 调用 Gemini/OpenAI-compatible 模型生成 SQL。
- `text2sql_evolver/runners/cached_runner.py`: 如果提供了缓存预测，就复用缓存；否则 fallback 到 LLM runner。
- `text2sql_evolver/inner_runner.py`: prompt 构造和 SQL 生成函数，供 LLM runner 使用。
- `text2sql_evolver/llm.py`: OpenAI-compatible client 封装和 SQL 抽取逻辑。

### Evaluators

- `text2sql_evolver/judge.py`: 只读 SQL safety guard、SQL 执行、执行结果比较。
- `text2sql_evolver/evaluators/execution_judge.py`: 对 `judge_sql` 的对象封装。
- `text2sql_evolver/evaluators/metrics.py`: accuracy 和 failure-count 指标。

### Analyzers

- `text2sql_evolver/analyzers/base.py`: analyzer 接口。
- `text2sql_evolver/analyzers/sql_specialized.py`: 默认 SQL-aware analyzer。
- `text2sql_evolver/sql_analyzer.py`: detector 逻辑，包括 clause mismatch、schema/table mismatch、join、aggregation、filtering、ordering、result shape、ratio/numeric warning、value grounding、evidence usage。
- `text2sql_evolver/specialized_ops.py`: SQL-specialized evolver operations 的 registry，以及每个操作的实现状态。

### Memory

- `text2sql_evolver/failure_store.py`: 内存中的失败样例分组和 JSON 写出。
- `text2sql_evolver/memory/failure_store.py`: memory 层对 failure storage 的别名封装。
- `text2sql_evolver/memory/history_store.py`: 记录 example run、patch decision、rollback 等事件历史。

### Editors

- `text2sql_evolver/skill_manager.py`: 规则模板和 skill 文件 patch 应用逻辑。
- `text2sql_evolver/editors/patch_generator.py`: 把 failures 转成 patch 文本，可选用 LLM。
- `text2sql_evolver/editors/skill_editor.py`: 把 patch 应用到 `SKILL.md`，并创建备份。

### Validators

- `text2sql_evolver/validators/acceptance.py`: 根据 manual apply 或 validation accuracy delta 决定接受/拒绝 patch。
- `text2sql_evolver/validators/validation_runner.py`: 重新跑 validation split，并计算执行准确率。
- `text2sql_evolver/validators/rollback.py`: 如果验证失败，恢复 skill 备份。

### Benchmarks

- `text2sql_evolver/bird_adapter.py`: 把官方 BIRD JSON 或旧 ShapleyRoute log 转成项目 JSONL。
- `text2sql_evolver/benchmarks/bird.py`: benchmark 层对 BIRD 转换能力的导出。
- `text2sql_evolver/benchmarks/splits.py`: deterministic update/validation/holdout split 工具。
- `text2sql_evolver/benchmarks/make_self_update_splits.py`: 创建 self-update benchmark splits 的 CLI。

### Reports

- `text2sql_evolver/reports/json_reporter.py`: 写出 `summary.json`、`examples.json`、`failures.json`、`skill_patch.md`。
- `text2sql_evolver/reports/markdown_reporter.py`: 写出 `report.md`。

### Utilities

- `text2sql_evolver/utils/paths.py`: dataset 和 database 路径解析。
- `text2sql_evolver/utils/io.py`: prediction JSONL 加载和共享写文件工具。

## 报告输出

每次运行 `text2sql-evolve` 会写出：

- `summary.json`: 模型、准确率、失败类别统计、patch decision、specialized operation registry。
- `examples.json`: 每条样例的 SQL、正确性、执行结果行、analyzer details。
- `failures.json`: 错题和 detector evidence。
- `skill_patch.md`: proposed learned rules，也就是建议写入 skill 的规则。
- `report.md`: 方便人读的摘要。
- `history.json`: example run 和 patch decision 的事件轨迹。
