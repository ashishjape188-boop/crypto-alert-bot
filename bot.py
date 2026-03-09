import pandas as pd
import numpy as np
import requests
import time
import os
from datetime import datetime, timedelta,UTC


def wait_until_next_candle():

    now = datetime.now(UTC)

    # next 30-minute boundary
    if now.minute < 30:
        target = now.replace(minute=30, second=2, microsecond=0)
    else:
        target = (now + timedelta(hours=1)).replace(minute=0, second=2, microsecond=0)

    sleep_seconds = (target - now).total_seconds()

    print(f"Waiting {sleep_seconds:.0f} seconds for next candle...")

    time.sleep(max(0, sleep_seconds))

# ==========================
# TELEGRAM SETTINGS
# ==========================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_IDS = [
    os.getenv("CHAT_ID"),
    os.getenv("CHAT_ID_2")
]

def send_alert(message):

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    for chat_id in CHAT_IDS:

        if not chat_id:
            continue

        requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": message
            }
        )

print("Crypto alert bot started...")

symbol = "ETHUSD"

last_candle_time = None
alert_count = 0
last_alert_time = 0


# ==========================
# RSI FUNCTION
# ==========================

def calculate_rsi(series, length=14):

    delta = series.diff()

    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)

    gain = pd.Series(gain, index=series.index)
    loss = pd.Series(loss, index=series.index)

    avg_gain = gain.ewm(alpha=1/length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


while True:

    wait_until_next_candle()

    try:

        # ==========================
        # FETCH DATA FROM DELTA
        # ==========================

        end = int(time.time())
        start = end - 200 * 1800   # 200 candles of 30m

        url = "https://api.delta.exchange/v2/history/candles"

        params = {
            "symbol": symbol,
            "resolution": "30m",
            "start": start,
            "end": end
        }

        response = requests.get(url, params=params)
        data = response.json()

        candles = data["result"]

        df = pd.DataFrame(candles)

        df = df.rename(columns={"time": "Open_time"})

        df["Open_time"] = pd.to_datetime(df["Open_time"], unit='s')

        df = df.sort_values("Open_time")

        # ==========================
        # INDICATORS
        # ==========================

        # Typical Price
        df["hlc3"] = (df["high"] + df["low"] + df["close"]) / 3
        df["ma"] = df["hlc3"].rolling(window=60).mean()

        # Mean Deviation
        df["mean_dev"] = df["hlc3"].rolling(window=60).apply(
            lambda x: np.mean(np.abs(x - np.mean(x))),
            raw=True
        )

        # CCI Formula
        df["CCI_60"] = (df["hlc3"] - df["ma"]) / (0.015 * df["mean_dev"])

        # ✅ CCI EMA 7 (Smoothing)
        df["CCI_EMA"] = df["CCI_60"].ewm(span=7, adjust=False).mean()

        # ✅ EMA 7 and EMA 200
        df["EMA7"] = df["Close"].ewm(span=7, adjust=False).mean()
        df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

        # RSI
        df["RSI"] = calculate_rsi(df["close"])

        # Difference
        df["Diff_CCI"] = df["CCI_60"] - df["CCI_EMA"]

        # ==========================
        # LAST CANDLE DATA
        # ==========================

        last = df.iloc[-2]

        candle_time = (last["Open_time"] + pd.Timedelta(hours=5, minutes=30)).strftime("%d-%b %H:%M IST")

        open_price = round(last["open"], 2)
        high_price = round(last["high"], 2)
        low_price = round(last["low"], 2)
        close_price = round(last["close"], 2)

        rsi_val = round(last["RSI"], 2)
        cci_val = round(last["CCI_60"], 2)
        diff_val = round(last["Diff_CCI"], 2)

        price = close_price

        # ==========================
        # SIGNAL LOGIC
        # ==========================

        candle_time_check = df.iloc[-2]["Open_time"]

        if candle_time_check != last_candle_time:
            last_candle_time = candle_time_check
            alert_count = 0

        buy_signal = (
            last["CCI_60"] > last["CCI_EMA"]
            and abs(last["Diff_CCI"]) > 4
            and (price > last["EMA200"] or price > last["EMA7"])
        )

        sell_signal = (
            last["CCI_60"] < last["CCI_EMA"]
            and abs(last["Diff_CCI"]) > 4
            and (price < last["EMA200"] or price < last["EMA7"])
        )

        current_time = time.time()

        allow_alert = (
            alert_count < 1
            and current_time - last_alert_time >= 900
        )

        # ==========================
        # TELEGRAM ALERTS
        # ==========================

        if buy_signal and allow_alert:

            message = f"""
🚀 LONG SIGNAL

ETHUSDT | 30m
━━━━━━━━━━━━━━━━

🕒 Candle : {candle_time}

📈 Open   : {open_price}
📈 High   : {high_price}
📉 Low    : {low_price}
📊 Close  : {close_price}

━━━━━━━━━━━━━━━━

📊 Indicators

RSI      : {rsi_val}
CCI      : {cci_val}
CCI Diff : {diff_val}

━━━━━━━━━━━━━━━━
⚡ Strategy: CCI + EMA + SMA
"""

            send_alert(message)

            alert_count += 1
            last_alert_time = current_time


        if sell_signal and allow_alert:

            message = f"""
🔻 SHORT SIGNAL

ETHUSDT | 30m
━━━━━━━━━━━━━━━━

🕒 Candle : {candle_time}

📈 Open   : {open_price}
📈 High   : {high_price}
📉 Low    : {low_price}
📊 Close  : {close_price}

━━━━━━━━━━━━━━━━

📊 Indicators

RSI      : {rsi_val}
CCI      : {cci_val}
CCI Diff : {diff_val}

━━━━━━━━━━━━━━━━
⚡ Strategy: CCI + EMA + SMA
"""
            if not buy_signal and not sell_signal and allow_alert:

                message = f"""
⚪ NO TRADE

ETHUSDT | 30m
━━━━━━━━━━━━━━━━

🕒 Candle : {candle_time}

📈 Open   : {open_price}
📈 High   : {high_price}
📉 Low    : {low_price}
📊 Close  : {close_price}

━━━━━━━━━━━━━━━━

📊 Indicators

RSI      : {rsi_val}
CCI      : {cci_val}
CCI Diff : {diff_val}

━━━━━━━━━━━━━━━━
⚡ Strategy: CCI + EMA
"""

        send_alert(message)
    
        alert_count += 1
        last_alert_time = current_time


    except Exception as e:

        print("Error occurred:", str(e))

        import traceback
        traceback.print_exc()

        print("Retrying in 60 seconds...")

        time.sleep(60)
