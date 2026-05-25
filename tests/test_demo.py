from text2sql_evolver.demo import main


def test_demo_runs_without_api(capsys):
    main()

    output = capsys.readouterr().out
    assert "Self-reskilling Text-to-SQL demo" in output
    assert "67/100" in output
    assert "53/100" in output
    assert "22/50" in output
    assert "257/500" in output
