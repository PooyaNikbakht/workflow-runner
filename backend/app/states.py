"""Step and run state machines. Every status change in the engine goes through `check_*`."""

from typing import Literal

StepStatus = Literal[
    "pending", "queued", "running", "needs_review", "completed", "failed", "skipped"
]
RunStatus = Literal["queued", "running", "needs_review", "completed", "failed", "rejected"]

STEP_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"queued", "skipped"}),
    "queued": frozenset({"running", "skipped"}),
    # running -> running: a worker crashed mid-step and another one took the expired lease.
    # running -> queued: a transient failure waiting for its retry.
    "running": frozenset({"running", "queued", "needs_review", "completed", "failed"}),
    "needs_review": frozenset({"completed"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "skipped": frozenset(),
}

RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "failed"}),
    "running": frozenset({"running", "needs_review", "completed", "failed"}),
    "needs_review": frozenset({"running", "completed", "rejected"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "rejected": frozenset(),
}

TERMINAL_RUN = frozenset({"completed", "failed", "rejected"})
DONE_STEP = frozenset({"completed", "skipped", "failed"})


class InvalidTransition(Exception):
    pass


def check_step(current: str, new: str) -> None:
    if new not in STEP_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(f"step can't go from {current} to {new}")


def check_run(current: str, new: str) -> None:
    if new not in RUN_TRANSITIONS.get(current, frozenset()):
        raise InvalidTransition(f"run can't go from {current} to {new}")
