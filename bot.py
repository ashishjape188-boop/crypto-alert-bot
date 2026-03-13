#!/usr/bin/env python
# coding: utf-8

# Crypto Signal Bot — ETHUSDT
#
# Automated trading signal bot using CCI(60), EMA 7, and RSI(14)
# on 30-minute candles from Delta Exchange.
# Sends Telegram alerts on signal changes and logs them to signals.csv.
#
# Strategy Logic:
# - Long Entry  → CCI > CCI_EMA, |Diff_CCI| > 4, Close > EMA7
# - Short Entry → CCI < CCI_EMA, |Diff_CCI| > 4, Close < EMA7
# - No Trade    → Conditions not met
#
# Designed to run as a Railway cron job (runs once and exits).
# Railway cron schedule: 0,30 * * * *

import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import pytz

# ── Configuration ────────────────────────────────────────────────
BOT_TOKEN = os.environ["BOT_TOKEN"]

CHAT_IDS = os.environ.get("CHAT_IDS", "1070509960,1937479700,5034473353,2037873693").split(",")

SYMBOL = os.environ.get("SYMBOL", "ETHUSDT")
IST = pytz.timezone("Asia/Kolkata")
SIGNALS_FILE = "signals.csv"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

print(f"[CONFIG] Symbol: {SYMBOL}")
print(f"[CONFIG] Chat IDs loaded: {len(CHAT_IDS)}")


def load_last_signal():
    """Load the most recent signal from signals.csv to survive restarts."""
    if os.path.exists(SIGNALS_FILE):
        try:
            df = pd.read_csv(SIGNALS_FILE)
            if not df.empty and "Signal" in df.columns:
                signal = df["Signal"].iloc[-1]
                print(f"[STATE] Restored last_signal from CSV: {signal}")
                return signal
        except Exception as e:
            print(f"[WARN] Could not load last signal from CSV: {e}")
    return None


last_signal = load_last_signal()


# ── Telegram Messenger ──────────────────────────────────────────

def send_message(text):
    """Send a message to all configured Telegram chat IDs."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        chat_id = chat_id.strip()
        try:
            r = requests.post(
                url,
                data={"chat_id": chat_id, "text": text},
                timeout=10
            )
            r.raise_for_status()
            print(f"[TELEGRAM] Message sent to {chat_id}")
        except Exception as e:
            print(f"[ERROR] Telegram failed for {chat_id}: {e}")


# ── Technical Indicators ────────────────────────────────────────

def calculate_rsi(series, length=14):
    """Wilder's RSI using EWM (alpha = 1/length). Returns Series of RSI values (0-100)."""
    delta = series.diff()
    gain = pd.Series(np.where(delta > 0, delta, 0), index=series.index)
    loss = pd.Series(np.where(delta < 0, -delta, 0), index=series.index)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# ── Fetch Candle Data ───────────────────────────────────────────

def fetch_candles(symbol=SYMBOL, resolution="30m", lookback_candles=200):
    """Fetch OHLCV candles from Delta Exchange API with retry logic."""
    end = int(time.time())
    start = end - lookback_candles * 1800

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                "https://api.delta.exchange/v2/history/candles",
                params={"symbol": symbol, "resolution": resolution, "start": start, "end": end},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()

            if "result" not in data or not data["result"]:
                raise ValueError("No candle data returned from API")

            break
        except Exception as e:
            print(f"[WARN] Fetch attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_DELAY)

    df = pd.DataFrame(data["result"])
    df.rename(columns={
        "time": "Open_time", "open": "Open", "high": "High",
        "low": "Low", "close": "Close", "volume": "Volume"
    }, inplace=True)

    df["Open_time"] = (
        pd.to_datetime(df["Open_time"], unit='s')
        .dt.tz_localize("UTC")
        .dt.tz_convert("Asia/Kolkata")
        .dt.tz_localize(None)
    )
    df = df.sort_values("Open_time").reset_index(drop=True)
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = df[col].astype(float)

    print(f"[FETCH] {len(df)} candles loaded. Latest: {df['Open_time'].iloc[-1]}")
    return df


# ── Compute Indicators & Generate Signal ────────────────────────

def compute_signals(df):
    """Compute CCI(60), EMA7, RSI(14) and derive trading signals."""
    # CCI (60)
    df["hlc3"] = (df["High"] + df["Low"] + df["Close"]) / 3
    df["ma"] = df["hlc3"].rolling(60).mean()
    df["mean_dev"] = df["hlc3"].rolling(60).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
    )
    df["CCI_60"] = (df["hlc3"] - df["ma"]) / (0.015 * df["mean_dev"])
    df["CCI_EMA"] = df["CCI_60"].ewm(span=7, adjust=False).mean()
    df["Diff_CCI"] = df["CCI_60"] - df["CCI_EMA"]

    # EMA 7 and RSI 14
    df["EMA7"] = df["Close"].ewm(span=7, adjust=False).mean()
    df["RSI"] = calculate_rsi(df["Close"])

    # Signal conditions
    long_cond = (df["CCI_60"] > df["CCI_EMA"]) & (df["Diff_CCI"].abs() > 4) & (df["Close"] > df["EMA7"])
    short_cond = (df["CCI_60"] < df["CCI_EMA"]) & (df["Diff_CCI"].abs() > 4) & (df["Close"] < df["EMA7"])
    df["Signal"] = np.where(long_cond, "Long Entry", np.where(short_cond, "Short Entry", "No Trade"))

    return df


# ── Main Signal-Check Job ──────────────────────────────────────

def run_signal_check():
    """Fetch data, compute signals, and send Telegram alert on signal change."""
    global last_signal
    print(f"[INFO] Job triggered at: {datetime.now(IST)}")

    try:
        df = fetch_candles()
    except Exception as e:
        print(f"[ERROR] API fetch failed after {MAX_RETRIES} attempts: {e}")
        return

    df = compute_signals(df)

    # Use second-to-last candle (last fully closed), not the open/incomplete latest candle
    row = df.iloc[-2]

    open_time = row["Open_time"].strftime("%Y-%m-%d %H:%M")
    close = row["Close"]
    signal = row["Signal"]
    rsi = round(row["RSI"], 2)

    print(f"[INFO] Signal: {signal} | Close: {close} | RSI: {rsi}")

    if signal != last_signal:
        emoji = "🟢" if signal == "Long Entry" else "🔴" if signal == "Short Entry" else "⚪"
        msg = (
            f"{emoji} *{SYMBOL} Signal Alert*\n"
            f"🕐 Time  : {open_time} IST\n"
            f"💰 Close : {close}\n"
            f"📊 Signal: {signal}\n"
            f"📈 RSI   : {rsi}"
        )
        send_message(msg)

        log = pd.DataFrame([{"Open_time": open_time, "Close": close, "Signal": signal, "RSI": rsi}])
        log.to_csv(SIGNALS_FILE, mode='a', header=not os.path.exists(SIGNALS_FILE), index=False)
        print(f"[LOG] Signal saved to {SIGNALS_FILE}")

        last_signal = signal
    else:
        print(f"[INFO] Signal unchanged ({signal}), no alert sent.")


# ── Entry Point (Railway Cron) ──────────────────────────────────

if __name__ == "__main__":
    time.sleep(5)  # wait for candle to finalize after the :00/:30 mark
    run_signal_check()
    print("[INFO] Job complete, process exiting.")