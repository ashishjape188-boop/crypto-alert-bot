import pandas as pd
import pandas_ta as ta
import requests
import time
import os

# TELEGRAM SETTINGS
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

coin_id = "ethereum"   # ETH
vs_currency = "usd"

def send_alert(message):

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=data)


def get_price_data():

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"

    params = {
        "vs_currency": vs_currency,
        "days": 1
    }

    response = requests.get(url, params=params)
    data = response.json()

    if "prices" not in data:
        print("CoinGecko API error:", data)
        return None

    prices = data["prices"]

    df = pd.DataFrame(prices, columns=["time","close"])

    df["time"] = pd.to_datetime(df["time"], unit="ms")

    # create OHLC approximation
    df["open"] = df["close"]
    df["high"] = df["close"]
    df["low"] = df["close"]
    df["volume"] = 0

    return df
print("Crypto alert bot started...")

last_candle_time = None
alert_count = 0
last_alert_time = 0


while True:

    try:

        df = get_price_data()

        if df is None:
            time.sleep(60)
            continue

        # indicators
        df["ema7"] = ta.ema(df["close"], length=7)
        df["sma7"] = ta.sma(df["close"], length=7)

        df["cci"] = ta.cci(df["high"], df["low"], df["close"], length=60)
        df["cci_ma"] = ta.sma(df["cci"], length=7)

        last = df.iloc[-1]
        prev = df.iloc[-2]

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
Symbol: ETH
Price: {price}
CCI crossed above CCI-MA
"""

            send_alert(message)

            alert_count += 1
            last_alert_time = current_time


        if sell_signal and allow_alert:

            message = f"""
🔻 SELL SIGNAL
Symbol: ETH
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
