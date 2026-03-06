import pandas as pd
import pandas_ta as ta
import requests
import time
import os

# TELEGRAM SETTINGS
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

symbol = "ETHUSDT"
interval = "30m"

def send_alert(message):

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=data)


def get_ohlcv():

    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": 200
    }

    data = requests.get(url, params=params).json()

    df = pd.DataFrame(data)[[0,1,2,3,4,5]]

    df.columns = ["time","open","high","low","close","volume"]

    df["time"] = pd.to_datetime(df["time"], unit="ms")

    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)

    return df


print("Crypto alert bot started...")

last_candle_time = None
alert_count = 0
last_alert_time = 0


while True:

    try:

        df = get_ohlcv()

        # EMA & SMA
        df["ema7"] = ta.ema(df["close"], length=7)
        df["sma7"] = ta.sma(df["close"], length=7)

        # CCI
        df["cci"] = ta.cci(df["high"], df["low"], df["close"], length=60)

        # CCI moving average
        df["cci_ma"] = ta.sma(df["cci"], length=7)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        candle_time = last["time"]

        if candle_time != last_candle_time:
            last_candle_time = candle_time
            alert_count = 0

        price = last["close"]

        buy_signal = (
            price > last["ema7"] and
            price > last["sma7"] and
            prev["cci"] < prev["cci_ma"] and
            last["cci"] > last["cci_ma"]
        )

        sell_signal = (
            price < last["ema7"] and
            price < last["sma7"] and
            prev["cci"] > prev["cci_ma"] and
            last["cci"] < last["cci_ma"]
        )

        current_time = time.time()

        allow_alert = (
            alert_count < 2 and
            current_time - last_alert_time >= 900
        )

        if buy_signal and allow_alert:

            message = f"""
🚀 BUY SIGNAL
Symbol: ETHUSDT
Price: {price}
CCI crossed above CCI-MA
"""

            send_alert(message)

            alert_count += 1
            last_alert_time = current_time


        if sell_signal and allow_alert:

            message = f"""
🔻 SELL SIGNAL
Symbol: ETHUSDT
Price: {price}
CCI crossed below CCI-MA
"""

            send_alert(message)

            alert_count += 1
            last_alert_time = current_time


        time.sleep(120)

    except Exception as e:

        print("Error:", e)

        time.sleep(60)
