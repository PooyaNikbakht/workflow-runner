import pytest

from app.states import (
    RUN_TRANSITIONS,
    STEP_TRANSITIONS,
    InvalidTransition,
    check_run,
    check_step,
)


@pytest.mark.parametrize(
    ("current", "new"),
    [
        ("pending", "queued"),
        ("queued", "running"),
        ("running", "completed"),
        ("running", "queued"),  # transient failure, waiting for a retry
        ("running", "running"),  # lease expired and another worker took over
        ("running", "needs_review"),
        ("needs_review", "completed"),
        ("running", "failed"),
        ("pending", "skipped"),
    ],
)
def test_allowed_step_transitions(current, new):
    check_step(current, new)


@pytest.mark.parametrize(
    ("current", "new"),
    [
        ("pending", "running"),
        ("pending", "completed"),
        ("queued", "completed"),
        ("completed", "running"),
        ("failed", "queued"),
        ("needs_review", "running"),
        ("skipped", "queued"),
    ],
)
def test_rejected_step_transitions(current, new):
    with pytest.raises(InvalidTransition):
        check_step(current, new)


def test_terminal_states_have_no_exits():
    for status in ("completed", "failed", "skipped"):
        assert STEP_TRANSITIONS[status] == frozenset()
    for status in ("completed", "failed", "rejected"):
        assert RUN_TRANSITIONS[status] == frozenset()


def test_run_transitions():
    check_run("queued", "running")
    check_run("running", "needs_review")
    check_run("needs_review", "running")
    check_run("needs_review", "rejected")
    with pytest.raises(InvalidTransition):
        check_run("completed", "running")
    with pytest.raises(InvalidTransition):
        check_run("queued", "needs_review")
