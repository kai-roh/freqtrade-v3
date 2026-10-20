from v3.phase1.transfers import BalanceRoute, choose_balance_route


def test_sufficient_wallets_use_direct_submit_without_fake_transfer_state():
    result = choose_balance_route(
        wallets_sufficient=True,
        transfer_capability_verified=False,
        transfer_authorized=False,
    )
    assert result.route == BalanceRoute.DIRECT_SUBMIT


def test_insufficient_wallets_transfer_only_when_capability_and_authorization_are_explicit():
    transfer = choose_balance_route(
        wallets_sufficient=False,
        transfer_capability_verified=True,
        transfer_authorized=True,
    )
    blocked = choose_balance_route(
        wallets_sufficient=False,
        transfer_capability_verified=False,
        transfer_authorized=True,
    )

    assert transfer.route == BalanceRoute.INTERNAL_TRANSFER
    assert blocked.route == BalanceRoute.ABORT
