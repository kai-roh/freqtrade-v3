import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from v3.phase1.run_control import RunAction, RunBounds, decide_next_episode, load_run_bounds

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 9, 16, tzinfo=UTC)


def bounds(**overrides):
    values = dict(
        maximum_episodes=3,
        episode_interval_seconds=120,
        maximum_total_run_seconds=3600,
        telegram_failure_pause_threshold=3,
    )
    values.update(overrides)
    return RunBounds(**values)


def decide(intents, *, now=None, last_closed_at=None, failures=0, **overrides):
    return decide_next_episode(
        intents=intents,
        now=now or T0 + timedelta(seconds=600),
        started_at=T0,
        bounds=bounds(**overrides),
        last_closed_at=last_closed_at,
        consecutive_telegram_failures=failures,
    )


def test_open_episode_is_always_resumed_before_any_stop_rule():
    intents = [("a", "CLOSED", T0), ("b", "HEDGED", T0)]
    decision = decide(intents, failures=9, now=T0 + timedelta(days=2))
    assert decision.action == RunAction.RESUME_EPISODE and decision.intent_id == "b"
    assert decide([("a", "ABORTING", T0), ("b", "HEDGED", T0)]).action == RunAction.STOP


def test_stop_rules_are_explicit_and_ordered():
    assert decide([], failures=3).reason.startswith("telegram_pause")
    assert decide([], now=T0 + timedelta(hours=2)).reason == "run_window_exhausted"
    closed = [(str(i), "CLOSED", T0) for i in range(3)]
    assert decide(closed).reason == "episode_budget_complete"
    decision = decide([("a", "CLOSED", T0)], last_closed_at=T0 + timedelta(seconds=580))
    assert decision.action == RunAction.WAIT and 90 <= decision.wait_seconds <= 101
    decision = decide([("a", "CLOSED", T0)], last_closed_at=T0 + timedelta(seconds=400))
    assert decision.action == RunAction.START_EPISODE and decision.reason == "episode 2 of 3"


def test_run_bounds_fail_closed():
    with pytest.raises(ValueError, match="maximum_episodes"):
        bounds(maximum_episodes=101)
    with pytest.raises(ValueError, match="60 seconds"):
        bounds(episode_interval_seconds=30)
    with pytest.raises(ValueError, match="8 days"):
        bounds(maximum_total_run_seconds=9 * 24 * 3600)
    assert bounds(maximum_episodes=1, episode_interval_seconds=0).maximum_episodes == 1


@pytest.mark.parametrize(
    "name,episodes",
    [
        ("phase1-engineering.json", 1),
        ("phase1-week-run.json", 60),
        ("phase1-verify-repeat.json", 2),
    ],
)
def test_committed_configs_load_as_run_bounds(name, episodes):
    loaded = load_run_bounds(ROOT / "configs" / name)
    assert loaded.maximum_episodes == episodes
    assert loaded.telegram_failure_pause_threshold == 3


def test_episode_interval_must_cover_the_episode_window(tmp_path):
    data = json.loads((ROOT / "configs" / "phase1-week-run.json").read_text())
    data["episode_interval_seconds"] = 600
    path = tmp_path / "week.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="cover one full episode window"):
        load_run_bounds(path)
