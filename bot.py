#!/usr/bin/env python
# coding: utf-8

import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime
import pytz

# =========================
# ⚙️ CONFIG
# =========================
BOT_TOKEN = "8749089704:AAFq_Xh6_oYk61V4mv8eNVdcX3Yh27AJuuY"

CHAT_IDS = ["5034473353"]

SYMBOL = "ETHUSDT"
IST = pytz.timezone("Asia/Kolkata")

# =========================
# 🔄 LOAD LAST SIGNAL
# =========================
def load_last_signal():
    if os.path.exists("signals.csv"):
        df = pd.read_csv("signals.csv")
        if len(df) > 0:
            return df.iloc[-1]["Signal"]
    return None

last_signal = load_last_signal()

# =========================
# 📩 TELEGRAM
# =========================
def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        try:
            requests.post(url, data={"chat_id": chat_id, "text": text})
        except Exception as e:
            print("Telegram Error:", e)

# =========================
# 📊 RSI
# =========================
def calculate_rsi(series, length=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    gain = pd.Series(gain, index=series.index)
    loss = pd.Series(loss, index=series.index)

    avg_gain = gain.ewm(alpha=1/length).mean()
    avg_loss = loss.ewm(alpha=1/length).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# =========================
# 📥 FETCH DATA
# =========================
def fetch_candles():
    end = int(time.time())
    start = end - 200 * 1800

    resp = requests.get(
        "https://api.delta.exchange/v2/history/candles",
        params={"symbol": SYMBOL, "resolution": "30m", "start": start, "end": end}
    )

    data = resp.json()["result"]

    df = pd.DataFrame(data)

    df.rename(columns={
        "time": "Open_time",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    }, inplace=True)

    df["Open_time"] = pd.to_datetime(df["Open_time"], unit='s')
    df = df.sort_values("Open_time").reset_index(drop=True)

    return df

# =========================
# 🧠 SIGNAL LOGIC
# =========================
def compute_new_signal(df):
    df = df.copy()

    df["hlc3"] = (df["High"] + df["Low"] + df["Close"]) / 3
    df["ma"] = df["hlc3"].rolling(60).mean()

    df["mean_dev"] = df["hlc3"].rolling(60).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
    )

    df["CCI_60"] = (df["hlc3"] - df["ma"]) / (0.015 * df["mean_dev"])
    df["CCI_EMA"] = df["CCI_60"].ewm(span=7).mean()

    df["EMA7"] = df["Close"].ewm(span=7).mean()
    df["RSI"] = calculate_rsi(df["Close"])

    signals = []

    for i in range(len(df)):
        if i == 0:
            signals.append("No Trade")
            continue

        close = df["Close"].iloc[i]
        ema = df["EMA7"].iloc[i]
        cci = df["CCI_60"].iloc[i]
        cci_ema = df["CCI_EMA"].iloc[i]

        prev_close = df["Close"].iloc[i-1]
        prev_ema = df["EMA7"].iloc[i-1]
        prev_cci = df["CCI_60"].iloc[i-1]
        prev_cci_ema = df["CCI_EMA"].iloc[i-1]

        prev_signal = signals[i-1]

        # CONTINUATION
        if prev_signal == "Long Trade" and close > ema and cci > cci_ema:
            signals.append("Long Trade")
            continue

        if prev_signal == "Short Trade" and close < ema and cci < cci_ema:
            signals.append("Short Trade")
            continue

        # NEW ENTRY
        if (prev_close < prev_ema and prev_cci < prev_cci_ema) and (close > ema and cci > cci_ema):
            signals.append("Long Trade")

        elif (prev_close > prev_ema and prev_cci > prev_cci_ema) and (close < ema and cci < cci_ema):
            signals.append("Short Trade")

        else:
            signals.append("No Trade")

    df["Final_Signal"] = signals
    return df

# =========================
# 📡 TELEGRAM FORMAT
# =========================
def get_message(df):
    row = df.iloc[-1]

    signal = row["Final_Signal"]

    emoji = "🟢" if signal == "Long Trade" else "🔴" if signal == "Short Trade" else "⚪"

    msg = f"""
{emoji} {SYMBOL}
Time: {row['Open_time']}
Close: {row['Close']}
Signal: {signal}
RSI: {round(row['RSI'],2)}
"""
    return signal, msg

# =========================
# 🚀 MAIN FUNCTION
# =========================
def run_signal_check():
    global last_signal

    df = fetch_candles()
    df = compute_new_signal(df)

    signal, msg = get_message(df)

    print("Current:", signal, "| Last:", last_signal)

    if signal != last_signal and signal != "No Trade":
        send_message(msg)

        log = pd.DataFrame([{
            "Time": df.iloc[-1]["Open_time"],
            "Signal": signal
        }])

        log.to_csv("signals.csv", mode='a', header=not os.path.exists("signals.csv"), index=False)

        last_signal = signal

    else:
        print("No new signal")

# =========================
# ▶️ RUN
# =========================
run_signal_check()
