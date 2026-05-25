---
name: query-writing
description: For writing precise SQLite queries for Text-to-SQL tasks.
---

# Query Writing Skill

Use this skill when answering a natural-language question by writing one read-only SQLite `SELECT` query.

## Core Workflow

1. Identify the requested answer columns or aggregate.
2. Identify filters, joins, grouping, ordering, and limits.
3. Write the simplest SQL that returns exactly the requested answer.
4. Keep the SQL executable in SQLite.

## Mandatory Pre-SQL Plan

Before writing SQL, silently make this plan:

- `answer_columns`: columns or expressions that the question asks to return.
- `condition_columns`: columns used only for filtering, joining, grouping, or ordering.
- `join_path`: tables and join keys needed to connect answer columns and condition columns.
- `aggregation`: whether the question asks for count, sum, average, max/min, ratio, percentage, or difference.
- `outer_select`: the final SELECT clause.

### Projection Check

- `outer_select` must contain only `answer_columns`.
- Do not project helper columns used only for WHERE, JOIN, GROUP BY, HAVING, ORDER BY, or LIMIT.
- If the question asks for first name and last name as separate fields, return them as separate columns unless it explicitly asks for one concatenated string.

### Result Shape Check

- For list/name/category/entity questions over joins, use `DISTINCT` when duplicate rows are likely.
- For "how many" questions, return one count expression unless grouped counts are explicitly requested.
- For top/bottom/highest/lowest/least/most questions, use explicit `ORDER BY` direction and `LIMIT`.

### Aggregation Check

- Use `SUM` for total consumption, total amount, total sales, total spent, and other cumulative quantities.
- For highest/lowest monthly or yearly totals, group by the requested time unit or entity, then order by the aggregate.
- Do not replace a requested total with `MAX(single_row_value)` unless the question asks for a single-row maximum.

### Ratio And Percentage Check

- Define numerator and denominator directly from the wording and evidence.
- Follow evidence formulas exactly; if evidence says divide by 12 or use a specific population, keep that formula.
- Use `CAST(... AS REAL)` or another REAL expression for division.
- Keep all denominator filters that define the population.
- Do not add `DISTINCT` to numerator or denominator unless the question or evidence explicitly asks for unique entities.
- Return only the final ratio, percentage, rate, or difference unless intermediate values are requested.

### Value Lookup Policy

- Preserve date, time, entity, category, status, and description filters from the question and evidence.
- Use evidence-provided normalized values when present, such as `2012/8/24` -> `2012-08-24`.
- Do not drop a filter just to make the query simpler.
- The execution harness may normalize high-confidence literal formats after generation.

## Safety

- Return exactly one read-only SQLite query.
- Never use `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `PRAGMA`, `ATTACH`, or `DETACH`.
- Do not invent tables or columns that are absent from the schema.
