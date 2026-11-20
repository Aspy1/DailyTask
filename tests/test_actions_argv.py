"""Keep delegated argv compatible with the actions CLI's equals syntax."""

import pytest
from helpers import read_json, run

import scripts.actions as actions

DAY = "2026-11-23"


@pytest.mark.parametrize(("argv", "filename", "selector", "expected"), [
    (["add_task", "--title=new task", f"--due={DAY}"],
     "tasks.json", ("tasks", 1, "title"), "new task"),
    (["complete_task", "--id=t_001"],
     "tasks.json", ("archived", 0, "status"), "completed"),
    (["add_course", "--name=new course", "--day=2", "--slots=2-3"],
     "courses.json", ("courses", 1, "day_of_week"), 2),
    (["update_course", "--id=c_001", "--day=3"],
     "courses.json", ("courses", 0, "day_of_week"), 3),
    (["add_plan", f"--date={DAY}", "--title=new plan", "--slot=5"],
     "daily_logs.json", ("plans", DAY, 1, "time_slot"), 5),
    (["complete_plan", f"--date={DAY}", "--index=0"],
     "daily_logs.json", ("plans", DAY, 0, "done"), True),
])
def test_delegated_bridge_argv_executes_all_six_actions(
        sandbox, argv, filename, selector, expected) -> None:
    assert run(f'add_task --title "existing task" --due {DAY}').startswith("OK")
    assert run('add_course --name "existing course" --day 1').startswith("OK")
    assert run(f'add_plan --date {DAY} --title "existing plan"').startswith("OK")

    result = actions.run_argv_in_process(argv)

    assert result.startswith(f"OK {argv[0]}"), result
    value = read_json(sandbox, filename)
    for part in selector:
        value = value[part]
    assert value == expected
    assert type(value) is type(expected)


@pytest.mark.parametrize("value", [
    "", "123", "--due=2030-01-01", "x=y=z", "white space",
    """'single' and "double"; & $(whoami)""",
])
def test_equals_values_remain_literal_in_delegated_namespace(sandbox, value) -> None:
    namespace = actions._build_action_namespace(
        ["add_task", f"--title={value}", f"--due={DAY}", "--notes="])

    assert namespace.title == value
    assert isinstance(namespace.title, str)
    assert namespace.notes == ""
    assert namespace.due == DAY


@pytest.mark.parametrize("title", [
    "123", "--due=2030-01-01", """a 'single' "double"; & $(whoami)""",
])
def test_delegated_equals_title_is_written_without_reinterpreting_it(sandbox, title) -> None:
    result = actions.run_argv_in_process(
        ["add_task", f"--title={title}", f"--due={DAY}", "--notes="])

    assert result.startswith("OK add_task"), result
    task = read_json(sandbox, "tasks.json")["tasks"][0]
    assert task["title"] == title
    assert task["notes"] == ""
    assert task["due_date"].startswith(DAY)


def test_legacy_separated_numeric_title_is_still_text(sandbox) -> None:
    result = actions.run_argv_in_process(["add_task", "--title", "123", "--due", DAY])

    assert result.startswith("OK add_task"), result
    assert read_json(sandbox, "tasks.json")["tasks"][0]["title"] == "123"


@pytest.mark.parametrize("argv", [
    ["add_course", "--name=A", "--day=not-an-integer"],
    ["add_task", "--title=A", f"--due={DAY}", "--unknown=value"],
    ["add_task", "--title=", f"--due={DAY}"],
])
def test_invalid_equals_argv_never_writes(sandbox, argv) -> None:
    result = actions.run_argv_in_process(argv)

    assert result.startswith("ERROR"), result
    assert not list(sandbox.rglob("*.json"))
