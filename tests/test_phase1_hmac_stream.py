import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment

from v3.phase1.binance_hmac_stream import DemoHmacSpotUserStream, Phase1DemoExecClientFactory


def stream_fixture(response):
    stream = object.__new__(DemoHmacSpotUserStream)
    stream._is_futures = False
    stream._ed25519_key = None
    stream._clock = SimpleNamespace(timestamp_ms=lambda: 1000)
    stream._api_key = "fixture-key"
    stream._get_sign = Mock(return_value="fixture-signature")
    stream._send_request = AsyncMock(return_value=response)
    stream._resume_dispatch = Mock()
    stream._subscription_id = None
    stream._is_authenticated = False
    return stream


def test_hmac_stream_does_not_claim_authentication_before_signed_ack():
    stream = stream_fixture({"status": 200, "result": {"subscriptionId": 0}})
    asyncio.run(stream.session_logon())
    assert not stream.is_authenticated
    assert stream._send_request.call_count == 0
    hook = AsyncMock()
    assert asyncio.run(stream.subscribe_user_data_stream(hook)) == "0"
    assert stream.is_authenticated
    method, params = stream._send_request.call_args.args
    assert method == "userDataStream.subscribe.signature"
    assert params == {"apiKey": "fixture-key", "timestamp": 1000, "signature": "fixture-signature"}
    hook.assert_awaited_once()
    stream._resume_dispatch.assert_called_once()


@pytest.mark.parametrize(
    "response",
    [
        {"status": 200, "result": {}},
        {"status": 401},
        {"status": 200, "result": {"subscriptionId": True}},
    ],
)
def test_invalid_signed_ack_never_authenticates_or_dispatches(response):
    stream = stream_fixture(response)
    with pytest.raises(ValueError):
        asyncio.run(stream.subscribe_user_data_stream())
    assert not stream.is_authenticated
    stream._resume_dispatch.assert_not_called()


def test_reconciliation_hook_failure_keeps_events_paused():
    stream = stream_fixture({"status": 200, "result": {"subscriptionId": 1}})
    with pytest.raises(RuntimeError):
        asyncio.run(
            stream.subscribe_user_data_stream(AsyncMock(side_effect=RuntimeError("fixture")))
        )
    assert not stream.is_authenticated
    assert stream._dispatch_paused
    stream._resume_dispatch.assert_not_called()


@pytest.mark.parametrize("field", ["base_url_http", "base_url_ws"])
def test_factory_rejects_endpoint_override_before_client_creation(field):
    config = SimpleNamespace(
        environment=BinanceEnvironment.DEMO, base_url_http=None, base_url_ws=None
    )
    setattr(config, field, "https://example.invalid")
    with pytest.raises(ValueError, match="endpoint overrides"):
        Phase1DemoExecClientFactory.create(None, None, config, None, None, None)


def test_intentional_unsubscribe_blocks_queued_recovery():
    stream = stream_fixture({})
    parent = "nautilus_trader.adapters.binance.websocket.user.BinanceUserDataWebSocketClient"
    with patch(parent + ".unsubscribe_user_data_stream", new_callable=AsyncMock):
        asyncio.run(stream.unsubscribe_user_data_stream())
    with patch(parent + "._resubscribe_locked", new_callable=AsyncMock) as recovery:
        assert asyncio.run(stream._resubscribe_locked()) is False
        recovery.assert_not_called()


def test_unexpected_stream_termination_keeps_upstream_recovery():
    stream = stream_fixture({})
    parent = "nautilus_trader.adapters.binance.websocket.user.BinanceUserDataWebSocketClient"
    with patch(parent + "._resubscribe_locked", new_callable=AsyncMock) as recovery:
        recovery.return_value = True
        assert asyncio.run(stream._resubscribe_locked()) is True
        recovery.assert_awaited_once()
