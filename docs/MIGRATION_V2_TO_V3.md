# V2 to V3 infrastructure migration

## Outcome

V2 was retired with 194 closed dry-run trades, zero open trades, and cumulative PnL of -183.83960848 USDT. Its container and Compose network were removed after a clean shutdown.

V3 takes over the existing localhost port 8080 and container identity `freqtrade_kai`, preserving the host tunnel, restart behavior, and health monitoring. The V3 project remains at `/home/kai/freqtrade-v3` and uses a new database and zero-entry strategy.

The migrated service started at `2026-08-10T05:00:16Z`. Docker reported `healthy`, the worker changed to `RUNNING`, the API returned `{"status":"pong"}`, and the new database contained zero total/open trades.

## Backup evidence

The full V2 project, including its database, market data, models, logs, backtests, and server configuration, is stored at:

```text
/home/kai/backups/freqtrade-v2/freqtrade-v2-full-20260810T045545Z.tar.zst
```

Verification values:

```text
SHA-256  971e4d77ceeebb9b5f1682b8a873ab598d84b5b715338ecd9327141398734bef
Size     3,615,018,524 bytes
Mode     0600 kai:kai
```

The SQLite integrity check, zstd stream test, and complete tar listing all passed. The adjacent `.sha256` file is also mode `0600`.

## Restore policy

Do not extract over either active project. For recovery:

1. Stop V3 and verify no container owns `freqtrade_kai`.
2. Revalidate the archive with `sha256sum -c` and `zstd -t`.
3. Extract into a new staging directory under `/home/kai/restore`.
4. Inspect the restored `.env`, database, and Compose configuration without printing secrets.
5. Restore V2 only through a separate, explicitly approved rollback decision.

The backup contains credentials and must never leave the protected server backup directory or be committed to GitHub.

## Active-test limits

The migrated V3 service is still `dry_run`. `V3ShadowStrategy` emits zero entries, and the V3 database is separate from V2. The test validates only container lifecycle, API reachability, configuration loading, persistence, and health reporting. It does not validate profitability and does not permit live trading.
