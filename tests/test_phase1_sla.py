import pytest

from v3.phase1.sla import summarize_phase1_sla


def test_sla_uses_quote_p99_with_100_percent_margin_and_labels_demo_hedge_lower_bound():
    quote = list(range(50))
    hedge = list(range(100, 150))

    result = summarize_phase1_sla(quote, hedge)

    assert result.quote_age.sample_count == 50
    assert result.maximum_quote_age_ms == 98
    assert result.hedge_latency_demo_lower_bound.median_ms == 124.5
    assert "lower-bound" in result.to_dict()["interpretation"]


def test_sla_rejects_too_few_or_negative_samples():
    with pytest.raises(ValueError, match="at least 50"):
        summarize_phase1_sla([1] * 49, [1] * 50)
    with pytest.raises(ValueError, match="non-negative"):
        summarize_phase1_sla([1] * 50, [-1] * 50)
