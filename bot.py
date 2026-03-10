import requests
import time
from datetime import datetime, timedelta
import pandas as pd
import os
import numpy as np

# ==========================
# TELEGRAM CONFIG
# ==========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

chat_ids = [
    "5034473353"
]

def send_message(text):
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text
        }
        requests.post(url, data=payload)

# ==========================
# WAIT FUNCTION
# ==========================

def wait_until_next_run():
    now = datetime.now()

    if now.minute < 30:
        target = now.replace(minute=30, second=0, microsecond=0)
    else:
        target = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

    sleep_seconds = (target - now).total_seconds()

    # ✅ Added 10 second delay to ensure candle is fully closed
    time.sleep(sleep_seconds + 10)

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


# ==========================
# BOT LOOP
# ==========================

last_signal = None
symbol = "ETHUSDT"

while True:

    print("Running at:", datetime.now())

    end = int(time.time())
    start = end - 200 * 1800

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

    df.rename(columns={
        "time": "Open_time",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume"
    }, inplace=True)

    df["Open_time"] = pd.to_datetime(df["Open_time"], unit='s')
    df = df.sort_values("Open_time")
    df.reset_index(drop=True, inplace=True)

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = df[col].astype(float)

    df = df.loc[:, ['Open_time', 'Open', 'Close', 'High', 'Low', 'Volume']]

    df['Open_time'] = pd.to_datetime(df['Open_time'])

    df['Open_time'] = (
        df['Open_time']
        .dt.tz_localize('UTC')
        .dt.tz_convert('Asia/Kolkata')
        .dt.tz_localize(None)
    )

    df2 = df.copy()

    # ==========================
    # CCI
    # ==========================

    df2["hlc3"] = (df2["High"] + df2["Low"] + df2["Close"]) / 3
    df2["ma"] = df2["hlc3"].rolling(window=60).mean()

    df2["mean_dev"] = df2["hlc3"].rolling(window=60).apply(
        lambda x: np.mean(np.abs(x - np.mean(x))), raw=True
    )

    df2["CCI_60"] = (df2["hlc3"] - df2["ma"]) / (0.015 * df2["mean_dev"])

    df2["CCI_EMA"] = df2["CCI_60"].ewm(span=7, adjust=False).mean()

    df2['OUTPUT'] = np.where(df2['CCI_60'] > df2.CCI_EMA, 'Pass', 'Fail')
    df2['Decision'] = np.where(df2['CCI_60'] > df2.CCI_EMA, 'Long', 'Short')

    # EMA
    df2["EMA7"] = df2["Close"].ewm(span=7, adjust=False).mean()
    df2['EMA7_CROSS'] = np.where(df2["Close"] > df2['EMA7'], 'Pass', 'Fail')

    # RSI
    df2['RSI'] = calculate_rsi(df2["Close"])
    df2['RSI_OUTPUT'] = np.where(df2['RSI'] > 40, 'Pass', 'Fail')

    # Difference
    df2['Diff_CCI'] = df2.CCI_60 - df2.CCI_EMA

    # ==========================
    # SIGNAL
    # ==========================

    df2['Signal'] = np.where(
        (df2['OUTPUT'] == 'Pass') & (abs(df2['Diff_CCI']) > 4) & (df2['EMA7_CROSS'] == 'Pass'),
        'Long Entry',
        np.where(
            (df2['OUTPUT'] == 'Fail') & (abs(df2['Diff_CCI']) > 4) & (df2['EMA7_CROSS'] == 'Fail'),
            'Short Entry',
            'No Trade'
        )
    )

    filtered_df = df2[["Open_time", "Signal", "Close"]]

    latest = filtered_df.tail(2).iloc[0]

    open_time = latest["Open_time"].strftime("%Y-%m-%d %H:%M")
    close = latest["Close"]
    signal = latest["Signal"]

    if signal != last_signal:

        msg = f"""
🚨 Trading Signal
Time: {open_time}
Closing Price: {close}
Signal: {signal}
"""

        send_message(msg)

        data = {
            "Open_time": [open_time],
            "Closing Price": [close],
            "Signal": [signal]
        }

        df_save = pd.DataFrame(data)

        file = "signals.xlsx"

        if not os.path.exists(file):
            df_save.to_excel(file, index=False)
        else:
            with pd.ExcelWriter(file, mode="a", engine="openpyxl", if_sheet_exists="overlay") as writer:
                df_save.to_excel(
                    writer,
                    index=False,
                    header=False,
                    startrow=writer.sheets["Sheet1"].max_row
                )

        last_signal = signal

    wait_until_next_run()
