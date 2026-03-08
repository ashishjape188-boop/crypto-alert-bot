import pandas as pd
import numpy as np
import requests
import time
import os

# ==========================
# TELEGRAM SETTINGS
# ==========================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = [os.getenv("CHAT_ID"),
           os.getenv("CHAT_ID_2")]

def send_alert(message):

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=data)


print("Crypto alert bot started...")

symbol = "ETHUSDT"

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

    try:

        # ==========================
        # FETCH DATA FROM DELTA
        # ==========================

        end = int(time.time())
        start = end - 200*1800   # 200 candles (30m)

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

        df = df.rename(columns={
            "time": "Open_time"
        })

        df["Open_time"] = pd.to_datetime(df["Open_time"], unit='s')

        df = df.sort_values("Open_time")

        # ==========================
        # INDICATORS
        # ==========================

        df["hlc3"] = (df["high"] + df["low"] + df["close"]) / 3
        df["ma"] = df["hlc3"].rolling(window=60).mean()

        df["mean_dev"] = df["hlc3"].rolling(window=60).apply(
            lambda x: np.mean(np.abs(x - np.mean(x))),
            raw=True
        )

        df["CCI_60"] = (df["hlc3"] - df["ma"]) / (0.015 * df["mean_dev"])

        df["CCI_EMA"] = df["CCI_60"].ewm(span=7, adjust=False).mean()

        df["SMA7"] = df["close"].rolling(window=7).mean()
        df["EMA7"] = df["close"].ewm(span=7, adjust=False).mean()

        df["RSI"] = calculate_rsi(df["close"])

        df["Diff_CCI"] = df["CCI_60"] - df["CCI_EMA"]

        last = df.iloc[-1]

        candle_time = last["Open_time"]

        if candle_time != last_candle_time:
            last_candle_time = candle_time
            alert_count = 0

        price = last["close"]

        buy_signal = (
            last["CCI_60"] > last["CCI_EMA"] and
            abs(last["Diff_CCI"]) > 4 and
            price > last["SMA7"] and
            price > last["EMA7"]
        )

        sell_signal = (
            last["CCI_60"] < last["CCI_EMA"] and
            abs(last["Diff_CCI"]) > 4 and
            price < last["SMA7"] and
            price < last["EMA7"]
        )

        current_time = time.time()

        allow_alert = (
            alert_count < 2 and
            current_time - last_alert_time >= 900
        )

        # ==========================
        # TELEGRAM ALERTS
        # ==========================

        if buy_signal and allow_alert:

            message = f"""
🚀 LONG ENTRY
Symbol: ETHUSDT
Price: {price}

CCI crossed above EMA
Diff CCI: {round(last["Diff_CCI"],2)}
RSI: {round(last["RSI"],2)}
"""

            send_alert(message)

            alert_count += 1
            last_alert_time = current_time


        if sell_signal and allow_alert:

            message = f"""
🔻 SHORT ENTRY
Symbol: ETHUSDT
Price: {price}

CCI crossed below EMA
Diff CCI: {round(last["Diff_CCI"],2)}
RSI: {round(last["RSI"],2)}
"""

            send_alert(message)

            alert_count += 1
            last_alert_time = current_time


        time.sleep(120)


    except Exception as e:

        print("Error:", e)
        time.sleep(60)
