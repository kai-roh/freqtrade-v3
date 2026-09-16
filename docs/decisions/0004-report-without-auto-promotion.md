# 0004 — Schedule reporting and research without automatic promotion

- Status: Accepted
- Date: 2026-08-10

## Context

V2 delivered a custom daily Telegram report at 23:00 KST. Its weekly view was an on-demand Freqtrade Telegram command rather than a scheduled research workflow. V3 also has one year of complete BTC/ETH futures candles and a deterministic walk-forward engine, but previously required manual execution and overwrote a fixed result path.

## Decision

Restore the familiar daily Telegram operations report and add a real scheduled weekly workflow. The weekly job refreshes 365 days of data, validates it, runs a near-full-year purged walk-forward with 180 training days and six 30-day validation folds, preserves an immutable timestamped result, and delivers a compact operations and research summary.

The external reporter has read-only API behavior. Freqtrade's built-in Telegram integration remains disabled. Telegram credentials stay only in the protected server `.env`, and reports are written atomically outside the container-owned `user_data` tree.

## Promotion boundary

A scheduled research run may report `ALLOW_CLASSIFIER_RESEARCH`, but it cannot edit strategy code, change the active strategy, restart the service, enable FreqAI, or authorize live trading. Promotion still requires an explicit reviewed change after all deterministic gates pass.

Repeating a failed candidate against newer data is monitoring, not improvement. New hypotheses must be implemented and reviewed separately; the schedule only measures them consistently.
