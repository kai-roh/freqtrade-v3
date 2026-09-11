"""Demo-only, version-pinned Spot HMAC signed user-stream compatibility.

Binance session.logon requires Ed25519. HMAC authenticates each subscription
using userDataStream.subscribe.signature instead. No order API is added here.
"""

from importlib.metadata import version

from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.adapters.binance.factories import BinanceLiveExecClientFactory
from nautilus_trader.adapters.binance.websocket.user import BinanceUserDataWebSocketClient


class DemoHmacSpotUserStream(BinanceUserDataWebSocketClient):
    async def connect(self):
        self._intentional_stop = False
        return await super().connect()

    async def unsubscribe_user_data_stream(self):
        self._intentional_stop = True
        return await super().unsubscribe_user_data_stream()

    async def disconnect(self):
        self._intentional_stop = True
        return await super().disconnect()

    async def _resubscribe_locked(self):
        # Binance emits stream termination even for our intentional unsubscribe.
        # Recheck under the upstream lock to cover already queued recovery tasks.
        if getattr(self, "_intentional_stop", False):
            return False
        return await super()._resubscribe_locked()

    async def session_logon(self):
        # No fake successful authentication: only subscription ACK may set this.
        self._is_authenticated = False
        return {"authentication_deferred_to_signed_subscription": True}

    async def subscribe_user_data_stream(self, pre_dispatch_hook=None):
        if self._is_futures or self._ed25519_key is not None:
            raise ValueError("compatibility stream is exclusively Spot HMAC")
        self._dispatch_paused = True
        self._is_authenticated = False
        timestamp = self._clock.timestamp_ms()
        params = {"apiKey": self._api_key, "timestamp": timestamp}
        params["signature"] = self._get_sign(f"apiKey={self._api_key}&timestamp={timestamp}")
        response = await self._send_request("userDataStream.subscribe.signature", params)
        subscription_id = response.get("result", {}).get("subscriptionId")
        if response.get("status") != 200 or type(subscription_id) is not int or subscription_id < 0:
            raise ValueError("signed subscription has no valid acknowledgment")
        self._subscription_id = str(subscription_id)
        if pre_dispatch_hook is not None:
            await pre_dispatch_hook()
        self._is_authenticated = True
        self._resume_dispatch()
        return self._subscription_id


class Phase1DemoExecClientFactory(BinanceLiveExecClientFactory):
    @staticmethod
    def create(loop, name, config, msgbus, cache, clock):
        if version("nautilus-trader") != "1.231.0" or config.environment != BinanceEnvironment.DEMO:
            raise ValueError("compatibility factory requires pinned 1.231.0 Demo")
        if config.base_url_http is not None or config.base_url_ws is not None:
            raise ValueError("compatibility factory forbids endpoint overrides")
        client = BinanceLiveExecClientFactory.create(loop, name, config, msgbus, cache, clock)
        original = client._ws_client
        if not original._is_futures and original._ed25519_key is None:
            client._ws_client = DemoHmacSpotUserStream(
                clock=original._clock,
                base_url=original._base_url,
                handler=original._handler,
                api_key=original._api_key,
                api_secret=original._hmac_secret,
                loop=original._loop,
                is_futures=False,
                is_ed25519=False,
                on_resubscribe=original._on_resubscribe,
                proxy_url=original._proxy_url,
            )
        return client
