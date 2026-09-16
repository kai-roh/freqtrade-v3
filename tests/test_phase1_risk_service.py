from datetime import UTC, datetime, timedelta
from pathlib import Path

from test_phase1_risk import _context

from v3.phase1.risk_service import Phase1RiskService

POLICY = Path(__file__).resolve().parents[1] / "configs/phase1-policy.json"


def _unmeasured_policy_path(tmp_path):
    import copy
    import json

    raw = json.loads(POLICY.read_text())
    unmeasured = copy.deepcopy(raw)
    for key in (
        "maximum_quote_age_ms",
        "quote_age_evidence",
        "quote_age_measured_at",
        "quote_age_p99_ms",
        "quote_age_sample_count",
    ):
        unmeasured["sla"][key] = None
    path = tmp_path / "phase1-policy-unmeasured.json"
    path.write_text(json.dumps(unmeasured, sort_keys=True))
    return path


def test_real_risk_process_denies_unmeasured_policy_and_closes(tmp_path):
    with Phase1RiskService(policy_path=_unmeasured_policy_path(tmp_path), timeout_seconds=3) as (
        service
    ):
        assert service._process.pid is not None
        decision = service.evaluate(_context(evaluated_at=datetime.now(UTC)))
        assert not decision.approved
        assert "quote-age SLA is unmeasured" in decision.reasons
    assert not service.evaluate(_context()).approved
    service.close()


def test_real_risk_process_applies_the_committed_measured_quote_sla():
    with Phase1RiskService(policy_path=POLICY, timeout_seconds=3) as service:
        decision = service.evaluate(_context(evaluated_at=datetime.now(UTC), quote_age_ms=97))
        assert not decision.approved
        assert "quote is stale" in decision.reasons
        assert "quote-age SLA is unmeasured" not in decision.reasons


def test_risk_process_rejects_stale_input():
    with Phase1RiskService(policy_path=POLICY, timeout_seconds=3) as service:
        decision = service.evaluate(
            _context(evaluated_at=datetime.now(UTC) - timedelta(seconds=10))
        )
        assert not decision.approved
        assert "risk service denied request" in " ".join(decision.reasons)


def test_risk_process_rejects_policy_hash_mismatch():
    with Phase1RiskService(policy_path=POLICY, timeout_seconds=3) as service:
        service.policy_hash = "0" * 64
        assert not service.evaluate(_context(evaluated_at=datetime.now(UTC))).approved


def test_dead_risk_process_never_approves():
    with Phase1RiskService(policy_path=POLICY, timeout_seconds=3) as service:
        service._process.terminate()
        service._process.join(timeout=2)
        decision = service.evaluate(_context(evaluated_at=datetime.now(UTC)))
        assert not decision.approved
        assert "unavailable" in " ".join(decision.reasons)
