---
name: query-writing
description: For writing and executing SQL queries - from simple single-table queries to complex multi-table JOINs and aggregations
---

# Query Writing Skill

## When to Use This Skill

Use this skill when you need to answer a question by writing and executing a SQL query.

## Workflow for Simple Queries

For straightforward questions about a single table:

1. **Identify the table** - Which table has the data?
2. **Get the schema** - Use `sql_db_schema` to see columns
3. **Write the query** - SELECT relevant columns with WHERE/LIMIT/ORDER BY
4. **Execute** - Run with `sql_db_query`
5. **Format answer** - Present results clearly

## Workflow for Complex Queries

For questions requiring multiple tables:

### 1. Plan Your Approach
**Use `write_todos` to break down the task:**
- Identify all tables needed
- Map relationships (foreign keys)
- Plan JOIN structure
- Determine aggregations

### 2. Examine Schemas
Use `sql_db_schema` for EACH table to find join columns and needed fields.

### 3. Construct Query
- SELECT - Columns and aggregates
- FROM/JOIN - Connect tables on FK = PK
- WHERE - Filters before aggregation
- GROUP BY - All non-aggregate columns
- ORDER BY - Sort meaningfully
- LIMIT - Default 5 rows

### 4. Validate and Execute
Check all JOINs have conditions, GROUP BY is correct, then run query.

## Example: Revenue by Country
```sql
SELECT
    c.Country,
    ROUND(SUM(i.Total), 2) as TotalRevenue
FROM Invoice i
INNER JOIN Customer c ON i.CustomerId = c.CustomerId
GROUP BY c.Country
ORDER BY TotalRevenue DESC
LIMIT 5;
```

## Quality Guidelines

- Query only relevant columns (not SELECT *)
- Always apply LIMIT (5 default)
- Use table aliases for clarity
- For complex queries: use write_todos to plan
- Never use DML statements (INSERT, UPDATE, DELETE, DROP)

## Mandatory Pre-SQL Plan

Before writing SQL, silently produce this internal plan and use it to draft the final query. This is mandatory, not an optional reminder.

### Projection Check
1. Set answer_columns to the exact entity, attribute, or metric requested by the question.
2. Set condition_columns to fields used only to filter or qualify the answer, including labels, statuses, dates, categories, joins, and HAVING counts.
3. Set outer_select to answer_columns only; keep condition_columns and helper expressions out of the final SELECT unless explicitly requested.
4. For "Which/List/Name X with condition Y" questions, SELECT X only and keep Y in WHERE, JOIN, GROUP BY, HAVING, ORDER BY, or subqueries.

### Result Shape Check
1. If the question asks to list, state, show, return, or name repeated entities or attributes, use DISTINCT unless duplicates are explicitly meaningful.
2. If the question asks "how many", project one count expression unless it asks for grouped counts.
3. If the question asks for one top/bottom/highest/lowest result, include ORDER BY with explicit direction and LIMIT 1.
4. If helper columns are needed for grouping, filtering, sorting, or ranking, use them internally without projecting them.

### Ratio And Percentage Check
1. Set numerator and denominator directly from the wording and evidence before writing SQL.
2. Use REAL arithmetic or CAST for division.
3. Project only the final requested ratio, percentage, rate, or deviation unless the question asks to show intermediate counts.
4. Do not output numerator or denominator helper counts as separate columns unless explicitly requested.

## Learned Rules From Validation Failures

These rules were generated from execution-based validation failures.
- **ordering_limit** (1 failures): For top/bottom/highest/lowest/latest questions, include ORDER BY with the correct direction, add LIMIT for requested ranks, and add a stable secondary tie-breaker such as name/title ascending when results can tie.
  - Detector evidence: ORDER BY, tie-breaker, or LIMIT mismatch
