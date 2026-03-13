# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Crypto trading signal bot that monitors ETHUSDT on Delta Exchange (30-minute candles) and sends Telegram alerts when signals change. Strategy uses CCI(60), CCI_EMA(7), EMA(7), and RSI(14).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot (starts scheduler, blocks)
python bot.py
```

Deployed as a Railway/Heroku worker process via `Procfile` (`worker: python bot.py`).

## Architecture

Single-file bot (`bot.py`) converted from a Jupyter notebook. The flow is:

1. **Startup** — Runs `run_signal_check()` once immediately, then starts APScheduler `BlockingScheduler`
2. **Scheduler** — `CronTrigger` fires at `:00:05` and `:30:05` IST (5 seconds after candle close to allow finalization)
3. **Each job cycle**: `fetch_candles()` → `compute_signals()` → compare with `last_signal` → alert on change → log to `signals.csv`

Key data flow:
- `fetch_candles()` — Pulls 200 candles from Delta Exchange REST API (`/v2/history/candles`), converts timestamps to IST
- `compute_signals()` — Calculates CCI(60), CCI_EMA(7-span EWM), EMA7, RSI(14), then derives Long Entry / Short Entry / No Trade
- `run_signal_check()` — Uses `df.iloc[-1]` (latest candle, which may be incomplete) and sends Telegram alerts only when signal changes from `last_signal`

`old_bot.py` is the previous version using a `while True` sleep loop instead of APScheduler; logs to `signals.xlsx` via openpyxl.

## Signal Logic

- **Long Entry**: CCI_60 > CCI_EMA AND |Diff_CCI| > 4 AND Close > EMA7
- **Short Entry**: CCI_60 < CCI_EMA AND |Diff_CCI| > 4 AND Close < EMA7
- **No Trade**: conditions not met
- Alerts only fire when the signal *changes* from the previous check (`last_signal` in-memory state, lost on restart).

## Known Issues (resolved)

The following issues have been fixed:
- Bot token now loaded from `BOT_TOKEN` environment variable (required)
- Chat IDs loaded from `CHAT_IDS` env var (comma-separated, with hardcoded defaults)
- Uses `df.iloc[-2]` (last closed candle) instead of `df.iloc[-1]` (possibly incomplete)
- `last_signal` restored from `signals.csv` on startup to prevent duplicate alerts
- Scheduler cron fixed from `minute="0,3"` to `minute="0,30"`
- API fetch includes retry logic (3 attempts with 5s delay)
- Wrapped in `if __name__ == "__main__"` guard
- Removed Jupyter notebook artifacts and dead code
- Removed unused `openpyxl` dependency

## Remaining Considerations

- **Always-on process** — `BlockingScheduler` keeps the container alive 24/7 on Railway even though the job only runs every 30 minutes. Consider Railway cron jobs for cost efficiency.

## Working Principles

- Scan and understand the codebase before making changes.
- Prefer small, safe, reversible improvements over broad rewrites.
- Preserve the current strategy intent unless a bug or inconsistency is clearly found.
- Do not edit files unless explicitly asked — first report findings and ask clarifying questions.
- When suggesting changes, show minimal patch-style diffs and flag assumptions.


