# V3 reporting and scheduled research

## Telegram reports

V3 uses the Telegram bot and chat previously assigned to V2, but keeps Freqtrade's built-in Telegram integration disabled. A separate read-only reporter queries the localhost API and cannot start, stop, or modify the trading service.

The installer verifies that the Oracle host timezone is `Asia/Seoul` before installing the schedules. Server schedules then use Korea Standard Time:

- every day at 23:00: operations report;
- every Sunday at 23:10: data refresh, walk-forward research, immutable result archive, and weekly report.

Both messages are labeled `V3` and `DRY-RUN`. They include period and cumulative trade counts and PnL, profit factor, win rate, open trades, and bot balance. The weekly message also includes the research decision, data end time, promoted-portfolio count, and strongest active candidate diagnostic.

Markdown copies are written atomically with mode `0600` under:

```text
reports/daily/YYYY-MM-DD.md
reports/weekly/YYYY-MM-DD.md
```

This host-owned directory is outside the Freqtrade `user_data` mount so ephemeral research containers cannot change its ownership. Telegram delivery failures return a non-zero status and do not print the bot token. Cron output is retained under `reports/logs`.

## One-year market data

The existing data is market data, not trained-model metadata. It contains one year of Binance futures candles for BTC and ETH at 15-minute and one-hour timeframes. Mark-price and funding-rate series also exist, but the current milestone does not consume them.

The original milestone used 90 training days. The scheduled full-year monitoring mode uses:

- 180 training days;
- a six-hour purge/embargo;
- 30 out-of-sample validation days;
- six walk-forward folds;
- 0.20% normal and 0.30% stress round-trip costs.
- Since 2026-09-15, trades are sized at 5% of capital (`capital_fraction_per_trade`),
  so drawdown is a portfolio measure. Earlier reports assumed 100% of capital per
  trade and are not comparable on drawdown or expectancy; profit factor is unaffected.
  Fold-boundary trades now resolve exits on later causal candles instead of closing
  at the fold's last candle. The first run on this basis
  (`research_results/validation-b6d3bbd/`) kept `STOP_BEFORE_CLASSIFIER` with
  identical trade counts and drawdowns of 2.2%–4.2%.

This requires the latest 360 days and six hours from the one-year store. A small leading overlap remains so candle boundaries and weekly refreshes do not make the run fail at the minimum-span edge.

This process is parameter selection and out-of-sample testing, not FreqAI or other machine-learning training. Classifier work remains blocked until at least one deterministic BTC/ETH portfolio passes all promotion gates.

## Weekly pipeline

`scripts/run_scheduled_research.sh` performs the following fail-closed sequence:

1. acquire a non-blocking host lock;
2. refresh 365 days of BTC/ETH futures candles;
3. validate the data and execute the deterministic walk-forward;
4. move complete results into `research_results/scheduled/<UTC-run-id>`;
5. atomically update `research_results/scheduled/latest`;
6. send the weekly operations and research summary.

Incomplete research calculations remain hidden and do not replace `latest`. Once a complete result becomes `latest`, a later Telegram delivery failure returns a non-zero job status but does not discard or roll back the valid research artifact. Historical scheduled outputs are server-local and ignored by Git.

The pipeline never changes strategy code, switches the active strategy, or authorizes live trading. A rejected result is still a valid completed research run and is reported as `STOP_BEFORE_CLASSIFIER`.

## Manual verification

```bash
cd /home/kai/freqtrade-v3
./scripts/run_operations_report.sh daily
./scripts/run_operations_report.sh weekly
./scripts/run_scheduled_research.sh
./deploy/install_server_cron.sh
crontab -l
```
