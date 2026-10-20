import pytest

from v3.phase1.binance_probe import SPOT_DEMO, USDM_DEMO
from v3.phase1.node_smoke import permitted_diagnostic_request


@pytest.mark.parametrize(
    "base,path",
    [(SPOT_DEMO, "/api/v3/order"), (USDM_DEMO, "/fapi/v1/order"), (USDM_DEMO, "/fapi/v1/leverage")],
)
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_node_diagnostic_denies_mutations(base, path, method):
    assert not permitted_diagnostic_request(base, method, path)


def test_node_diagnostic_allows_only_demo_reads_and_stream_lifecycle():
    assert permitted_diagnostic_request(USDM_DEMO, "GET", "/fapi/v3/account")
    assert permitted_diagnostic_request(USDM_DEMO, "POST", "/fapi/v1/listenKey")
    assert not permitted_diagnostic_request("https://fapi.binance.com", "GET", "/fapi/v3/account")
    assert not permitted_diagnostic_request(USDM_DEMO, "GET", "/fapi/v3/account?signature=hidden")
