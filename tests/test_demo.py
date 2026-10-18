from text2sql_evolver.demo import main


def test_demo_runs_without_api(capsys):
    main()

    output = capsys.readouterr().out
    assert "Self-reskilling Text-to-SQL demo" in output
    assert "Before / After Skill Checks" in output
    assert "Current Evaluation Results" not in output
