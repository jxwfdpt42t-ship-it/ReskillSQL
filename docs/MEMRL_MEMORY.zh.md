MemRL 经验记忆接入说明

本实现将 MemRL 核心代码接入 Text-to-SQL 演化流程；尚未开展模型效果实验。

**实际复用范围**

固定上游 https://github.com/MemTensor/MemRL 的提交
`c1b322ca43de36ddf64c6712f89d0095bfc35ce0`，保留 MIT 许可证、来源和原始校验值。
复用记忆构建器、Embedding provider、RLConfig、ValueAwareSelector、QValueUpdater。
代码位于 `text2sql_evolver/_vendor/memrl/`，SQL 适配位于 `text2sql_evolver/memory/`。

第一阶段用 Embedding 余弦相似度门槛召回最多 10 条；第二阶段调用上游
ValueAwareSelector，按 Q 值排序、相似度打破并列，取最多 3 条。探索率固定为 0。
它是上游已有的选择器路径，不是论文中归一化 similarity/Q 混合打分的精确复现。
Q 更新直接调用上游 QValueUpdater，默认 alpha=0.1、gamma=0：
`Q_new = (1-alpha) * Q_old + alpha * reward`。

持久化采用本地 SQLite 适配层，不需要运行 MemOS 服务。真实运行必须配置真实
Embedding 模型；没有使用词袋或随机向量冒充语义检索。

**执行与学习流程**

1. SQL 生成前按当前数据库及 Schema 范围检索历史经历；旧失败明确标记为失败，
   历史内容作为参考证据。新任务的 gold SQL 不交给生成模型。
2. 每次模型 SQL 尝试及确定性改写均记录 SQL、阶段、执行错误和结果行数。
   外层用 gold 判定每次尝试的正确性，区分直接成功、最终失败和修复后成功。
   只知道最终 SQL 的缓存记录标记为 success_trace_unavailable，不能冒称直接成功。
3. 修复后成功提供权重 0.6 的信号，其失败尝试也进入可修复性筛选；失败仍为 1.0，
   风险成功为 0.4，冗长成功为 0.25。最终正确率仍按最终输出计算。
4. 补丁生成前检索相关历史经验并加入证据包。
5. 完成新旧 Skill 对照后，再保存本轮经历和更新 Q，避免边验证边学习。
6. 任务记忆同时保存结构化原始证据和可检索文本。默认调用上游 proceduralization
   builder（通过本项目的总结提示词）生成总结并附带记录；总结失败时回退到原始证据，
   明确记录 fallback 状态。`trajectory` 模式不增加总结模型调用。
7. 无论候选是否晋升，验证中的局部改善、局部退化及整次候选结果都可以入库。
   被拒绝的候选不是经过验证的通用规则；局部改善也不证明整个补丁有效。

记忆最初 Q 为 0，与产生记忆时的成败分开。实际复用后再更新：推理端按最终任务
正确性给 +1/-1；优化器端按候选是否通过现有验证门禁给 +1/-1，与是否开启自动应用分开。
同次调用中实际放入上下文的多条记忆共享反馈；这不是对每条记忆贡献的严格因果归因。
Q 按消费者（inference/optimizer）、模型名称和 Skill 内容哈希隔离。
反馈事件有幂等 ID，并在 SQLite 事务内更新，重复提交不会重复计分。

同时修复了原来的运行时 Skill 压缩：现在保留实际规则文本，新规则不再因不属于固定标题而丢失。
候选验证抛异常也会恢复原 Skill。现有 gate 的 weak_pass 接受策略没有在本次变更中重定义。
由于实际 Skill 提示词内容发生变化，旧准确率记录不能直接当作新实现的对照结果。

**开启方式**

默认 `memory_mode=off`，不会悄悄启动额外模型／Embedding 调用。

在现有模型配置之外设置：

```bash
export TEXT2SQL_MEMORY_EMBEDDING_MODEL='你的兼容 Embedding 模型名称'
export TEXT2SQL_MEMORY_EMBEDDING_BASE_URL='你的 Embedding 服务地址'
export TEXT2SQL_MEMORY_EMBEDDING_API_KEY='你的 Embedding 服务密钥'
```

Embedding 地址和密钥未单独设置时使用现有模型服务配置，但该服务必须支持 embeddings。
数据路径需要替换为你实际准备的开发数据。

```bash
uv run text2sql-evolve \
  --dataset data/update.jsonl \
  --validation-dataset data/validation.jsonl \
  --memory-mode learn \
  --memory-build proceduralization
```

不加 `--auto-apply` 时，候选经过验证后不会自动晋升，但已验证的实验经验仍会入库。
若只希望外循环检索，加 `--memory-optimizer-only`。
若暂不希望增加经验总结的 LLM 调用，使用 `--memory-build trajectory`；Embedding 仍需服务调用。
默认库是 `data/memrl/experiences.sqlite`，可通过 `--memory-path` 指定隔离库。

冻结记忆评测：

```bash
uv run text2sql-live-skill-compare \
  --dataset data/final_holdout.jsonl \
  --before-skill skills/query-writing/versions/query-writing-v0002.md \
  --after-skill skills/query-writing/SKILL.md \
  --memory-mode read
```

live compare 只读取 MemRL 库，不写经验、不更新 Q。其原有 regression_memory.jsonl
输出仍可能写入诊断结果，但本实现不会自动导入该旧文件（它包含历史 holdout 来源）。
两个 Skill 使用基线 Skill 的同一 Q 上下文，记忆在比较中冻结。
`agent.py` 的独立 DeepAgents 交互入口未接入此适配；接入入口是 evolver 的 LLMRunner
及 live-skill-compare。缓存预测不能用于衡量记忆增强，因此 evolve 在开启记忆时拒绝 --predictions。

**数据隔离与范围**

- 学习来源只允许 update/validation；拒绝显式 holdout/test 来源及常见同名路径。
- 本轮全部任务的相同问题与 source_id（没有时用 id）从检索中排除，包括候选经验的来源链。
- 数据构造时必须保留稳定 source_id；改写问题并换掉源 ID，系统无法自动识别同源污染。
- 旧拒绝补丁仍走原有兼容路径；旧回归库不会自动迁移进新 MemRL 库。
- 检索默认限定同一数据库绝对路径及 Schema 哈希。跨库迁移不在本次实现范围内。
- 这不是用户画像系统，也未实现自动语义去重、淘汰或独立记忆控制器。
- 每次命令按顺序执行；不支持多进程共享 Skill 文件并同时演化。评测期间也不要让另一个进程写同一记忆库。
- 库内保留原始 SQL 和历史评测证据，作为本地实验数据管理。不要将最终 holdout 用于调参或手工构建记忆。

**本地验证**

```bash
uv run pytest -q
```

测试使用临时 SQLite、固定测试向量和模拟模型，覆盖失败经验复用、跨运行持久化、
Q 更新及幂等、来源隔离、Schema 失效、SQL 修复轨迹、候选拒绝后保留经验和异常恢复。
它们验证代码行为，不代表准确率提升；后续需独立设计 A/B 和跨轮实验。
