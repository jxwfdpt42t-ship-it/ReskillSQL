# 面试讲解稿

## 一句话

ReskillSQL 是一个面向 Text-to-SQL 的自我更新 Agent：内层负责写 SQL，外层根据执行轨迹更新 query-writing skill，并用 validation/holdout 控制更新是否真的有效。

## 我解决的问题

普通 Text-to-SQL agent 失败后通常只重试或反思一次，不能把长期错误沉淀成可复用能力。这个项目把失败轨迹转成结构化证据，再生成候选 skill，并通过 SQL-aware gate 验证后才接受。

## 系统结构

```text
问题 + schema + skill
  -> inner runner 生成 SQL
  -> judge 执行并比较结果
  -> outer evolver 分析失败
  -> optimizer 生成 skill patch
  -> validation gate 接受或拒绝
  -> 版本化保存 skill
```

## 可以重点讲的点

- 为什么更新 skill 而不是微调模型。
- 为什么要区分 update / validation / holdout。
- SQL-aware attribution 如何定位 projection、aggregation、ordering、value grounding 等错误。
- regression memory 如何避免新 skill 伤害旧样本。
- self-update benchmark 为什么看的是“更新过程”，不是只看最终准确率。

## 实验状态

当前仓库公开实现、评测协议和复现实验入口，不公开正式效果数字。最终结论将在 BIRD 派生 benchmark、Gemini 2.5 Flash 配置、Skill/Memory 2×2 对照和 holdout 协议冻结后统一报告。
