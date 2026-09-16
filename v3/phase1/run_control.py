"""Pure decisions for the bounded Demo repetition runner.

The runner owns one manifest. Between episodes it asks this module what to do
next from durable facts only: the intents recorded under the manifest, the wall
clock, and the notification delivery history. Nothing here submits orders or
talks to the venue, and every stop reason is explicit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class RunAction(StrEnum):
    START_EPISODE = "start_episode"
    RESUME_EPISODE = "resume_episode"
    WAIT = "wait"
    STOP = "stop"


@dataclass(frozen=True)
class RunBounds:
    maximum_episodes: int
    episode_interval_seconds: int
    maximum_total_run_seconds: int
    telegram_failure_pause_threshold: int

    def __post_init__(self) -> None:
        if type(self.maximum_episodes) is not int or not 1 <= self.maximum_episodes <= 100:
            raise ValueError("maximum_episodes must be an integer in [1, 100]")
        if type(self.episode_interval_seconds) is not int or self.episode_interval_seconds < 0:
            raise ValueError("episode_interval_seconds must be a non-negative integer")
        if self.maximum_episodes > 1 and self.episode_interval_seconds < 60:
            raise ValueError("repeated episodes require at least 60 seconds between episodes")
        if (
            type(self.maximum_total_run_seconds) is not int
            or not 30 <= self.maximum_total_run_seconds <= 8 * 24 * 3600
        ):
            raise ValueError("maximum_total_run_seconds must be an integer in [30, 8 days]")
        if (
            type(self.telegram_failure_pause_threshold) is not int
            or self.telegram_failure_pause_threshold < 1
        ):
            raise ValueError("telegram_failure_pause_threshold must be a positive integer")


def load_run_bounds(path: Path) -> RunBounds:
    data = json.loads(Path(path).read_text())
    bounds = RunBounds(
        data["maximum_episodes"],
        data["episode_interval_seconds"],
        data["maximum_total_run_seconds"],
        data["telegram_failure_pause_threshold"],
    )
    if data["maximum_run_seconds"] > bounds.maximum_total_run_seconds:
        raise ValueError("a single episode window cannot exceed the total run window")
    if (
        bounds.maximum_episodes > 1
        and data["maximum_run_seconds"] > bounds.episode_interval_seconds
    ):
        raise ValueError("episode interval must cover one full episode window")
    return bounds


@dataclass(frozen=True)
class RunDecision:
    action: RunAction
    reason: str
    intent_id: str | None = None
    wait_seconds: int = 0


def decide_next_episode(
    *,
    intents: list[tuple[str, str, datetime]],
    now: datetime,
    started_at: datetime,
    bounds: RunBounds,
    last_closed_at: datetime | None,
    consecutive_telegram_failures: int,
) -> RunDecision:
    """Choose the next runner step.

    ``intents`` holds ``(intent_id, state, created_at)`` for this manifest only.
    An open episode is always resumed first; no stop rule may abandon inventory.
    """
    open_intents = [row for row in intents if row[1] != "CLOSED"]
    if len(open_intents) > 1:
        return RunDecision(
            RunAction.STOP, "ambiguous: more than one open episode for this manifest"
        )
    if open_intents:
        return RunDecision(
            RunAction.RESUME_EPISODE, "open episode must finish first", open_intents[0][0]
        )
    closed = len(intents) - len(open_intents)
    if consecutive_telegram_failures >= bounds.telegram_failure_pause_threshold:
        return RunDecision(RunAction.STOP, "telegram_pause: repeated delivery failures")
    elapsed = (now - started_at).total_seconds()
    if elapsed >= bounds.maximum_total_run_seconds:
        return RunDecision(RunAction.STOP, "run_window_exhausted")
    if closed >= bounds.maximum_episodes:
        return RunDecision(RunAction.STOP, "episode_budget_complete")
    if last_closed_at is not None:
        since = (now - last_closed_at).total_seconds()
        if since < bounds.episode_interval_seconds:
            return RunDecision(
                RunAction.WAIT,
                "episode interval not elapsed",
                wait_seconds=int(bounds.episode_interval_seconds - since) + 1,
            )
    return RunDecision(
        RunAction.START_EPISODE, f"episode {closed + 1} of {bounds.maximum_episodes}"
    )
