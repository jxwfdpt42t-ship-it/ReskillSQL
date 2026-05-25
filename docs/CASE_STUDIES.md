# Case Studies

These examples show what the self-reskilling loop is meant to learn: reusable SQL behavior, not one-off answer patches.

## Case 1: Projection / Duplicate Rows

**Question**

```text
State the category of events were held at MU 215.
```

**Failure pattern**

The old query joined event and budget tables and returned duplicate category rows.

```sql
SELECT T2.category
FROM event AS T1
INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event
WHERE T1.location = 'MU 215';
```

**Reskilled behavior**

For list/category/entity outputs over joins, the live-safe skill asks the agent to reason about result shape and use `DISTINCT` when duplicate rows are likely.

```sql
SELECT DISTINCT T2.category
FROM event AS T1
INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event
WHERE T1.location = 'MU 215';
```

**Reusable lesson**

This is not tied to one table. It transfers to list/name/category questions where joins multiply answer rows.

## Case 2: Aggregation / Monthly Total

**Question**

```text
What is the highest monthly consumption in the year 2012?
```

**Failure pattern**

The old query can confuse maximum single-row consumption with highest monthly total.

```sql
SELECT MAX(Consumption)
FROM yearmonth
WHERE SUBSTR(Date, 1, 4) = '2012';
```

**Reskilled behavior**

The system learns that monthly totals require grouping by month, ordering by the aggregate, and limiting to the top month.

```sql
SELECT SUM(Consumption)
FROM yearmonth
WHERE SUBSTR(Date, 1, 4) = '2012'
GROUP BY SUBSTR(Date, 5, 2)
ORDER BY SUM(Consumption) DESC
LIMIT 1;
```

**Reusable lesson**

For highest/lowest monthly or yearly totals, decide whether the question asks for a single-row maximum or an aggregate over a time unit.

## Case 3: Value Grounding / Stored Literal Format

**Question**

```text
What is the status of the event which bought "Post Cards, Posters" on 2019/8/20?
```

**Failure pattern**

The old SQL may preserve the user-facing date format even when the database stores normalized dates.

```sql
SELECT status
FROM expense
WHERE expense_description = 'Post Cards, Posters'
  AND expense_date = '2019-8-20';
```

**Reskilled behavior**

The value lookup policy normalizes high-confidence date literals to the stored format.

```sql
SELECT status
FROM expense
WHERE expense_description = 'Post Cards, Posters'
  AND expense_date = '2019-08-20';
```

**Reusable lesson**

For entity/date/category filters, preserve semantic intent but normalize to values that actually appear in the database when confidence is high.

## Case 4: Live Skill Safety

The project originally found that long accumulated skill files can harm live generation by making the model output incomplete SQL. The current runtime uses a compressed live skill prompt while keeping full versioned skills on disk.

**Reusable lesson**

External agent skills need two forms:

- a versioned, auditable skill file for humans and the evolver
- a compact runtime prompt that the model can reliably follow

