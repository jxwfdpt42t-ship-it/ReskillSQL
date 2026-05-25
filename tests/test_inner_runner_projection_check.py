from text2sql_evolver.inner_runner import _apply_projection_check, apply_sql_skill_checks


def test_projection_check_removes_condition_column_from_select():
    sql = (
        "SELECT T1.molecule_id, T1.label FROM molecule AS T1 "
        "INNER JOIN atom AS T2 ON T1.molecule_id = T2.molecule_id "
        "WHERE T1.label = '-' GROUP BY T1.molecule_id HAVING COUNT(T2.atom_id) > 5;"
    )

    rewritten = _apply_projection_check(sql, "Which non-carcinogenic molecules consisted more than 5 atoms?")

    assert rewritten.startswith("SELECT T1.molecule_id FROM")
    assert "WHERE T1.label = '-'" in rewritten


def test_compiled_check_adds_distinct_for_list_queries():
    sql = "SELECT T2.category FROM event AS T1 JOIN budget AS T2 ON T1.id = T2.event_id WHERE T1.location = 'MU 215';"

    rewritten = apply_sql_skill_checks(
        sql,
        "State the category of events were held at MU 215.",
        "## Mandatory Pre-SQL Plan\n\n### Projection Check\nUse DISTINCT when list outputs can duplicate rows.\n",
    )

    assert rewritten.startswith("SELECT DISTINCT T2.category FROM")


def test_compiled_check_keeps_only_final_metric_projection():
    sql = (
        "SELECT SUM(CASE WHEN Admission = '+' THEN 1 ELSE 0 END) AS inpatient, "
        "SUM(CASE WHEN Admission = '-' THEN 1 ELSE 0 END) AS outpatient, "
        "CAST(SUM(CASE WHEN Admission = '+' THEN 1 ELSE 0 END) AS REAL) * 100 / "
        "SUM(CASE WHEN Admission = '-' THEN 1 ELSE 0 END) AS pct FROM Patient WHERE SEX = 'M';"
    )

    rewritten = apply_sql_skill_checks(
        sql,
        "Are there more in-patient or outpatient who were male? What is the deviation in percentage?",
        "## Mandatory Pre-SQL Plan\n\n### Ratio And Percentage Check\nProject only the final percentage metric.\n",
    )

    assert rewritten.startswith("SELECT CAST(")
    assert " AS inpatient" not in rewritten
    assert " AS outpatient" not in rewritten


def test_compiled_check_rewrites_highest_monthly_total():
    sql = "SELECT MAX(Consumption) FROM yearmonth WHERE SUBSTR(Date, 1, 4) = '2012';"

    rewritten = apply_sql_skill_checks(
        sql,
        "What is the highest monthly consumption in the year 2012?",
        "## Mandatory Pre-SQL Plan\n\n### Aggregation Check\nFor monthly totals, group by month.\n",
    )

    assert rewritten == (
        "SELECT SUM(Consumption) FROM yearmonth WHERE SUBSTR(Date, 1, 4) = '2012' "
        "GROUP BY SUBSTR(Date, 5, 2) ORDER BY SUM(Consumption) DESC LIMIT 1"
    )


def test_compiled_check_adds_non_null_for_observed_symptoms():
    sql = (
        "SELECT T1.Symptoms, T1.Diagnosis FROM Examination AS T1 "
        "INNER JOIN Patient AS T2 ON T1.ID = T2.ID ORDER BY T2.Birthday DESC LIMIT 1;"
    )

    rewritten = apply_sql_skill_checks(
        sql,
        "What are the symptoms observed by the youngest patient to ever did a medical examination?",
        "## Mandatory Pre-SQL Plan\n\n### Filtering Check\nObserved attributes should be non-null.\n",
    )

    assert "WHERE T1.Symptoms IS NOT NULL ORDER BY" in rewritten


def test_compiled_check_does_not_add_non_null_for_missing_symptoms():
    sql = (
        "SELECT COUNT(DISTINCT T1.ID) FROM Patient AS T1 "
        "INNER JOIN Examination AS T3 ON T1.ID = T3.ID "
        "WHERE T1.SEX = 'F' AND T3.Symptoms IS NULL;"
    )

    rewritten = apply_sql_skill_checks(
        sql,
        "How many female patients does not have any symptom?",
        "## Mandatory Pre-SQL Plan\n\n### Filtering Check\nObserved attributes should be non-null.\n",
    )

    assert rewritten == sql


def test_compiled_check_removes_ranking_helper_column_from_projection():
    sql = "SELECT player_name, height FROM Player ORDER BY height DESC LIMIT 1;"

    rewritten = apply_sql_skill_checks(
        sql,
        "Which player is the tallest?",
        "## Mandatory Pre-SQL Plan\n\n### Projection Check\nKeep helper ranking columns out of SELECT.\n",
    )

    assert rewritten == "SELECT player_name FROM Player ORDER BY height DESC LIMIT 1;"
