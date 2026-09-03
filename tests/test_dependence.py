import pandas as pd
import pytest

from v3.dependence import return_dependence_diagnostics


def test_return_dependence_reports_acf_and_ljung_box_by_lag():
    returns = pd.Series([1.0, -0.5, 0.25, -0.75, 0.5, 0.1, -0.2, 0.4])

    result = return_dependence_diagnostics(returns, maximum_lag=3)

    assert result.observation_count == 8
    assert [row.lag for row in result.lags] == [1, 2, 3]
    assert all(-1 <= row.autocorrelation <= 1 for row in result.lags)
    assert all(row.ljung_box_q >= 0 for row in result.lags)
    assert all(0 <= row.p_value <= 1 for row in result.lags)
    assert result.lags[2].ljung_box_q >= result.lags[1].ljung_box_q


def test_return_dependence_rejects_constant_or_invalid_series():
    with pytest.raises(ValueError, match="non-zero variance"):
        return_dependence_diagnostics(pd.Series([1, 1, 1]), maximum_lag=1)
    with pytest.raises(ValueError, match="finite"):
        return_dependence_diagnostics(pd.Series([1.0, float("nan"), 2.0]), maximum_lag=1)
    with pytest.raises(ValueError, match="observation_count"):
        return_dependence_diagnostics(pd.Series([1.0, 2.0]), maximum_lag=2)
