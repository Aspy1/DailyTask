"""Verification must parse the exact arguments sent across the CLI boundary."""

import shlex

import pytest

from src.services.ai_verify import parse_command


@pytest.mark.parametrize(
    "title",
    ["Read chapter two", "Alice's \"notes\"; $(ignored) & review", "--due=tomorrow", ""],
)
def test_verifier_round_trips_quoted_cli_arguments(title: str) -> None:
    command = shlex.join([
        "python", "scripts/actions.py", "add_task",
        f"--title={title}", "--due=2026-11-21",
    ])
    assert parse_command(command) == (
        "add_task", {"title": title, "due": "2026-11-21"},
    )


def test_verifier_accepts_separate_values_and_normalizes_flags() -> None:
    assert parse_command(
        'python scripts/actions.py add_plan --title "Read notes" --time-slot=2',
    ) == ("add_plan", {"title": "Read notes", "time_slot": "2"})


def test_verifier_rejects_unclosed_quotes() -> None:
    assert parse_command('python scripts/actions.py add_task --title "oops') == ("", {})
