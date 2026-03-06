import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
import os

# TELEGRAM SETTINGS
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# EXCHANGE
exchange = ccxt.binance()

symbol = "ETH/USDT"
timeframe = "30m"

def send_alert(message):

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=data)


print("Crypto alert bot started...")

last_candle_time = None
alert_count = 0
last_alert_time = 0


while True:

    try:

        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=200)

        df = pd.DataFrame(
            bars,
            columns=["time","open","high","low","close","volume"]
        )

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

        # Reset alert counter when new candle appears
        if candle_time != last_candle_time:
            last_candle_time = candle_time
            alert_count = 0

        price = last["close"]

        # BUY SIGNAL
        buy_signal = (
            price > last["ema7"] and
            price > last["sma7"] and
            prev["cci"] < prev["cci_ma"] and
            last["cci"] > last["cci_ma"]
        )

        # SELL SIGNAL
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